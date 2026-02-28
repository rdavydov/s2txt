import telebot
import speech_recognition as sr
import os
import numpy as np
import subprocess
import time
import logging
import threading
import uuid
import tempfile
import functools
import requests
from requests.exceptions import ReadTimeout, ConnectionError, HTTPError
from telebot import apihelper
import signal
import sys

# Настройка системы логирования для отслеживания работы бота
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),  # Сохранение логов в файл
        logging.StreamHandler()          # Вывод логов в консоль
    ]
)
logger = logging.getLogger(__name__)

# Получение токена и настроек из переменных окружения
TOKEN = os.getenv('TOKEN')
RECOGNITION_ENGINE = os.getenv('RECOGNITION_ENGINE', 'google')
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY', '')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID', '')


def _build_allowed_ids():
    """Составляет множество разрешённых ID из переменных окружения."""
    allowed = set()
    # Обратная совместимость: одиночный пользователь
    val = os.getenv('ALLOWED_USER_ID')
    if val:
        try:
            allowed.add(int(val))
        except ValueError:
            pass
    # Новый формат: несколько пользователей через запятую
    for part in os.getenv('ALLOWED_USER_IDS', '').split(','):
        part = part.strip()
        if part:
            try:
                allowed.add(int(part))
            except ValueError:
                pass
    return allowed


ALLOWED_USER_IDS = _build_allowed_ids()

# Если переменные окружения не установлены, пытаемся импортировать из конфига
if not TOKEN or not ALLOWED_USER_IDS:
    try:
        from config import TOKEN, ALLOWED_USER_ID
        ALLOWED_USER_IDS.add(int(ALLOWED_USER_ID))
    except ImportError:
        logger.error("Токен и ID пользователя не найдены!")
        sys.exit(1)

# Глобальная переменная для контроля работы бота
bot_running = True

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    global bot_running
    logger.info("Получен сигнал завершения. Останавливаем бота...")
    bot_running = False

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def safe_bot_operation(operation, *args, **kwargs):
    """
    Безопасное выполнение операций с ботом с повторными попытками
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return operation(*args, **kwargs)
        except (ReadTimeout, ConnectionError, HTTPError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Экспоненциальная задержка
                logger.warning(f"Ошибка {type(e).__name__} (попытка {attempt + 1}): {e}. Повторяем через {wait_time}с...")
                time.sleep(wait_time)
            else:
                logger.error(f"Не удалось выполнить операцию после {max_retries} попыток: {e}")
                raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при выполнении операции: {e}")
            raise

def run_bot():
    """
    Основная функция запуска и работы бота.
    Включает в себя механизмы обработки ошибок и автоматического перезапуска.
    """
    global bot_running
    
    # Настройка более коротких таймаутов для раннего обнаружения проблем
    apihelper.CONNECT_TIMEOUT = 10
    apihelper.READ_TIMEOUT = 20
    
    restart_count = 0
    max_restarts = 10  # Максимальное количество перезапусков подряд
    
    while bot_running and restart_count < max_restarts:
        bot = None
        try:
            logger.info(f"Запуск бота (попытка {restart_count + 1})...")
            bot = telebot.TeleBot(token=TOKEN, threaded=True)

            def authorized_only(func):
                """Декоратор: проверяет, что пользователь находится в списке разрешённых."""
                @functools.wraps(func)
                def wrapper(message, *args, **kwargs):
                    if message.from_user.id not in ALLOWED_USER_IDS:
                        safe_bot_operation(bot.reply_to, message, '🚫 Доступ запрещен. Извините.')
                        return
                    return func(message, *args, **kwargs)
                return wrapper

            def split_audio_file(input_file, temp_dir, chunk_duration=30):
                """
                Разбивает аудиофайл на части указанной длительности для облегчения распознавания.
                """
                try:
                    # Получаем длительность входного файла
                    result = subprocess.run([
                        'ffprobe',
                        '-v', 'error',
                        '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1',
                        input_file
                    ], capture_output=True, text=True, timeout=30)
                    
                    if result.returncode != 0:
                        raise subprocess.CalledProcessError(result.returncode, 'ffprobe')
                        
                    audio_duration = float(result.stdout.strip())
                    
                    chunk_paths = []
                    # Разбиваем файл на куски указанной длительности
                    for start in np.arange(0, audio_duration, chunk_duration):
                        end = min(start + chunk_duration, audio_duration)
                        chunk_filename = os.path.join(
                            temp_dir,
                            f'audio_chunk_{int(start)}_{uuid.uuid4().hex}.wav'
                        )

                        # Используем ffmpeg для создания куска аудио
                        result = subprocess.run([
                            'ffmpeg',
                            '-i', input_file,
                            '-ss', str(start),
                            '-to', str(end),
                            '-acodec', 'pcm_s16le',
                            '-ar', '44100',
                            '-y',  # Перезаписывать файлы без подтверждения
                            chunk_filename
                        ], capture_output=True, timeout=60)
                        
                        if result.returncode == 0:
                            chunk_paths.append(chunk_filename)
                        else:
                            logger.error(f"Ошибка ffmpeg: {result.stderr.decode()}")

                    return chunk_paths
                    
                except subprocess.TimeoutExpired:
                    logger.error("Таймаут при обработке аудио файла")
                    return []
                except Exception as e:
                    logger.error(f"Ошибка при разбиении аудио файла: {e}")
                    return []

            @bot.message_handler(commands=['start', 'help'])
            @authorized_only
            def send_welcome(message):
                """Обработчик команд start и help"""
                welcome_text = """
👋 Добро пожаловать в бот для распознавания речи!

🗣️ Отправьте мне голосовое сообщение, и я преобразую его в текст.
📝 Поддерживается русский язык.
⚡ Длинные сообщения автоматически разбиваются на части.
                """
                safe_bot_operation(bot.reply_to, message, welcome_text.strip())

            @bot.message_handler(func=lambda message: True, content_types=['text'])
            @authorized_only
            def text_processing(message):
                """Обработчик текстовых сообщений."""
                safe_bot_operation(bot.reply_to, message, '🗣️ Запишите голосовое сообщение, либо перешлите его мне.')

            @bot.message_handler(content_types=['voice'])
            @authorized_only
            def voice_processing(message):
                """Обработчик голосовых сообщений."""
                # Используем отдельный поток для обработки, чтобы не блокировать polling
                threading.Thread(target=process_voice_message, args=(bot, message), daemon=True).start()

            def process_voice_message(bot, message):
                """Обработка голосового сообщения в отдельном потоке"""
                status_msg = safe_bot_operation(bot.reply_to, message, '⌛ Скачивание аудио...')

                try:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        uid = uuid.uuid4().hex
                        ogg_filepath = os.path.join(temp_dir, f'audio_{uid}.ogg')
                        wav_filepath = os.path.join(temp_dir, f'audio_{uid}.wav')

                        # Получение и скачивание файла
                        file_id = message.voice.file_id
                        file_info = safe_bot_operation(bot.get_file, file_id)
                        
                        if not file_info:
                            raise Exception("Не удалось получить информацию о файле")
                            
                        downloaded_file = safe_bot_operation(bot.download_file, file_info.file_path)

                        # Сохранение скачанного файла
                        with open(ogg_filepath, 'wb') as new_file:
                            new_file.write(downloaded_file)

                        # Обновляем статус: конвертация
                        if status_msg:
                            try:
                                bot.edit_message_text(
                                    '🔄 Конвертация в WAV...',
                                    chat_id=status_msg.chat.id,
                                    message_id=status_msg.message_id
                                )
                            except Exception:
                                pass

                        # Конвертация из OGG в WAV с таймаутом
                        result = subprocess.run([
                            'ffmpeg',
                            '-i', ogg_filepath,
                            '-acodec', 'pcm_s16le',
                            '-ar', '44100',
                            '-y',
                            wav_filepath
                        ], capture_output=True, timeout=120)
                        
                        if result.returncode != 0:
                            raise subprocess.CalledProcessError(result.returncode, 'ffmpeg')

                        # Распознавание
                        process_recognition(bot, message, wav_filepath, temp_dir, status_msg)

                except subprocess.TimeoutExpired:
                    safe_bot_operation(bot.reply_to, message, '⚠️ Превышено время обработки файла.')
                    logger.error("Таймаут при конвертации аудио")
                except Exception as e:
                    safe_bot_operation(bot.reply_to, message, f'⚠️ Извините, произошла ошибка при подготовке: {str(e)}')
                    logger.error(f"Ошибка при обработке голосового сообщения: {e}")

            def process_recognition(bot, message, wav_filepath, temp_dir, status_msg):
                """Выполняет распознавание речи с использованием выбранного движка."""
                engine = RECOGNITION_ENGINE.lower()

                try:
                    if engine == 'whisper':
                        # Whisper: файл не разбивается на части
                        try:
                            import whisper
                        except ImportError:
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               '⚠️ Пакет whisper не установлен.')
                            return

                        if status_msg:
                            try:
                                bot.edit_message_text(
                                    '📝 Распознавание аудио целиком...',
                                    chat_id=status_msg.chat.id,
                                    message_id=status_msg.message_id
                                )
                            except Exception:
                                pass

                        model = whisper.load_model(WHISPER_MODEL)
                        result = model.transcribe(wav_filepath)
                        recognized_text = result.get('text', '').strip()

                        if recognized_text:
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               f'📄 {recognized_text}')
                        else:
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               '😔 К сожалению, не удалось распознать речь в аудиозаписи.')

                    elif engine == 'yandex':
                        # Yandex SpeechKit: файл не разбивается на части
                        if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               '⚠️ Не заданы YANDEX_API_KEY и/или YANDEX_FOLDER_ID.')
                            return

                        if status_msg:
                            try:
                                bot.edit_message_text(
                                    '📝 Распознавание аудио целиком...',
                                    chat_id=status_msg.chat.id,
                                    message_id=status_msg.message_id
                                )
                            except Exception:
                                pass

                        with open(wav_filepath, 'rb') as audio_file:
                            response = requests.post(
                                'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize',
                                headers={'Authorization': f'Api-Key {YANDEX_API_KEY}'},
                                params={'folderId': YANDEX_FOLDER_ID, 'lang': 'ru-RU'},
                                data=audio_file,
                                timeout=60
                            )

                        if response.status_code == 200:
                            recognized_text = response.json().get('result', '').strip()
                            if recognized_text:
                                safe_bot_operation(bot.send_message, message.chat.id,
                                                   f'📄 {recognized_text}')
                            else:
                                safe_bot_operation(bot.send_message, message.chat.id,
                                                   '😔 К сожалению, не удалось распознать речь в аудиозаписи.')
                        else:
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               f'⚠️ Ошибка Yandex SpeechKit: {response.status_code}')

                    else:
                        # Google (по умолчанию): разбиваем на 30-секундные части
                        chunk_paths = split_audio_file(wav_filepath, temp_dir)
                        if not chunk_paths:
                            safe_bot_operation(bot.reply_to, message, '⚠️ Не удалось обработать аудио файл.')
                            return

                        recognizer = sr.Recognizer()
                        # Настройка параметров распознавания для лучшей точности
                        recognizer.energy_threshold = 300
                        recognizer.dynamic_energy_threshold = True

                        total = len(chunk_paths)
                        recognized_parts = []

                        for i, chunk_path in enumerate(chunk_paths, 1):
                            if status_msg:
                                try:
                                    bot.edit_message_text(
                                        f'📝 Распознавание (часть {i} из {total})...',
                                        chat_id=status_msg.chat.id,
                                        message_id=status_msg.message_id
                                    )
                                except Exception:
                                    pass

                            try:
                                with sr.AudioFile(chunk_path) as source:
                                    # Настройка для устранения шума
                                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                                    audio_data = recognizer.record(source)
                                    
                                    # Распознавание речи с помощью Google Speech Recognition
                                    chunk_text = recognizer.recognize_google(
                                        audio_data, language='ru-RU')
                                    
                                    if chunk_text.strip():
                                        recognized_parts.append(chunk_text)

                            except sr.UnknownValueError:
                                logger.warning(f"Часть {i}: речь не распознана.")
                            except sr.RequestError as e:
                                logger.error(f"Ошибка сервиса распознавания для части {i}: {e}")
                            except Exception as e:
                                logger.error(f"Ошибка при распознавании части {i}: {e}")

                        if recognized_parts:
                            full_text = " ".join(recognized_parts)
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               f'📄 Полный текст:\n\n{full_text}')
                        else:
                            safe_bot_operation(bot.send_message, message.chat.id,
                                               '😔 К сожалению, не удалось распознать речь в аудиозаписи.')

                    # Обновляем статус: завершено
                    if status_msg:
                        try:
                            bot.edit_message_text(
                                '✅ Обработка завершена!',
                                chat_id=status_msg.chat.id,
                                message_id=status_msg.message_id
                            )
                        except Exception:
                            pass

                except Exception as e:
                    safe_bot_operation(bot.send_message, message.chat.id,
                                       f'⚠️ Извините, произошла ошибка при распознавании: {str(e)}')
                    logger.error(f"Общая ошибка при распознавании: {e}")

            # Запуск polling с оптимизированными параметрами
            logger.info("Бот успешно запущен и готов к работе!")
            bot.infinity_polling(
                timeout=20,           # Таймаут для получения обновлений
                long_polling_timeout=15,  # Таймаут для long polling
                logger_level=logging.WARNING,  # Меньше логов от библиотеки
                restart_on_change=False,
                allowed_updates=['message']  # Обрабатываем только сообщения
            )
            
        except (ReadTimeout, ConnectionError) as e:
            restart_count += 1
            wait_time = min(30 * restart_count, 300)  # Максимум 5 минут
            logger.warning(f"Ошибка соединения: {e}. Перезапуск через {wait_time} секунд...")
            if bot_running:
                time.sleep(wait_time)
        except KeyboardInterrupt:
            logger.info("Получен сигнал прерывания")
            bot_running = False
            break
        except Exception as e:
            restart_count += 1
            logger.error(f"Неожиданная ошибка: {e}")
            if bot_running and restart_count < max_restarts:
                wait_time = min(10 * restart_count, 60)
                logger.info(f"Перезапуск через {wait_time} секунд...")
                time.sleep(wait_time)
        finally:
            if bot and hasattr(bot, 'stop_polling'):
                try:
                    bot.stop_polling()
                except:
                    pass
            
            # Сброс счетчика при успешной работе более 10 минут
            if restart_count > 0:
                time.sleep(1)
    
    if restart_count >= max_restarts:
        logger.error(f"Достигнуто максимальное количество перезапусков ({max_restarts}). Завершение работы.")
    
    logger.info("Бот завершил работу")

if __name__ == '__main__':
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Работа бота прервана пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
