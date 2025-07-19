import telebot
import speech_recognition as sr
import os
import numpy as np
import subprocess
import time
import logging
import threading
from requests.exceptions import ReadTimeout, ConnectionError, HTTPError
from telebot import apihelper
import signal
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Получение токена и ID пользователя
TOKEN = os.getenv('TOKEN')
ALLOWED_USER_ID = os.getenv('ALLOWED_USER_ID')

if not TOKEN or not ALLOWED_USER_ID:
    try:
        from config import TOKEN, ALLOWED_USER_ID
    except ImportError:
        logger.error("Токен и ID пользователя не найдены!")
        sys.exit(1)

try:
    ALLOWED_USER_ID = int(ALLOWED_USER_ID)
except ValueError:
    logger.error("ALLOWED_USER_ID должен быть числом!")
    sys.exit(1)

# Настройка таймаутов для стабильной работы
apihelper.CONNECT_TIMEOUT = 10
apihelper.READ_TIMEOUT = 15

# Создание директории для временных файлов
TEMP_AUDIO_DIR = 'temp_audio'
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

# Глобальные переменные для контроля работы
bot_running = True
current_bot = None

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    global bot_running, current_bot
    logger.info("Получен сигнал завершения. Останавливаем бота...")
    bot_running = False
    
    # Принудительно останавливаем polling
    if current_bot:
        try:
            current_bot.stop_polling()
            logger.info("Polling остановлен")
        except Exception as e:
            logger.warning(f"Ошибка при остановке polling: {e}")

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup_temp_files():
    """Очистка всех временных файлов"""
    try:
        for filename in os.listdir(TEMP_AUDIO_DIR):
            filepath = os.path.join(TEMP_AUDIO_DIR, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        logger.info("Временные файлы очищены")
    except Exception as e:
        logger.warning(f"Ошибка при очистке временных файлов: {e}")

def safe_api_call(func, *args, max_retries=3, **kwargs):
    """Безопасное выполнение API вызовов с повторными попытками"""
    if not bot_running:
        return None
        
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (ReadTimeout, ConnectionError, HTTPError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Ошибка API (попытка {attempt + 1}): {e}. Повтор через {wait_time}с...")
                time.sleep(wait_time)
            else:
                logger.error(f"API вызов неудачен после {max_retries} попыток: {e}")
                raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка API: {e}")
            raise

def split_audio_file(input_file, chunk_duration=30):
    """Разбивает аудиофайл на части с улучшенной обработкой ошибок"""
    if not bot_running:
        return []
        
    try:
        # Получаем длительность файла с таймаутом
        result = subprocess.run([
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            input_file
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.error(f"Ошибка ffprobe: {result.stderr}")
            return []
            
        audio_duration = float(result.stdout.strip())
        logger.info(f"Длительность аудио: {audio_duration:.2f} секунд")

        chunk_paths = []
        for start in np.arange(0, audio_duration, chunk_duration):
            if not bot_running:
                break
                
            end = min(start + chunk_duration, audio_duration)
            chunk_filename = os.path.join(
                TEMP_AUDIO_DIR,
                f'audio_chunk_{int(start)}_{int(time.time())}.wav'
            )

            # Создаем чанк с таймаутом
            result = subprocess.run([
                'ffmpeg',
                '-i', input_file,
                '-ss', str(start),
                '-to', str(end),
                '-acodec', 'pcm_s16le',
                '-ar', '44100',
                '-y',  # Перезаписывать без подтверждения
                chunk_filename
            ], capture_output=True, timeout=60)
            
            if result.returncode == 0:
                chunk_paths.append(chunk_filename)
                logger.debug(f"Создан чанк: {chunk_filename}")
            else:
                logger.error(f"Ошибка создания чанка: {result.stderr.decode()}")

        return chunk_paths
        
    except subprocess.TimeoutExpired:
        logger.error("Таймаут при обработке аудио файла")
        return []
    except Exception as e:
        logger.error(f"Ошибка при разбиении аудио: {e}")
        return []

def run_bot():
    """Основная функция с улучшенной обработкой ошибок"""
    global bot_running, current_bot
    
    restart_count = 0
    max_restarts = 5
    
    while bot_running and restart_count < max_restarts:
        current_bot = None
        try:
            logger.info(f"Инициализация бота (попытка {restart_count + 1})...")
            current_bot = telebot.TeleBot(token=TOKEN, threaded=True)
            
            @current_bot.message_handler(commands=['start', 'help'])
            def send_welcome(message):
                """Команды приветствия"""
                if not bot_running:
                    return
                    
                if message.from_user.id != ALLOWED_USER_ID:
                    safe_api_call(current_bot.reply_to, message, '🚫 Доступ запрещен. Извините.')
                    return
                
                welcome_text = "👋 Бот для распознавания речи готов к работе!\n🗣️ Отправьте голосовое сообщение."
                safe_api_call(current_bot.reply_to, message, welcome_text)

            @current_bot.message_handler(func=lambda message: True, content_types=['text'])
            def text_processing(message):
                """Обработка текстовых сообщений"""
                if not bot_running:
                    return
                    
                if message.from_user.id != ALLOWED_USER_ID:
                    safe_api_call(current_bot.reply_to, message, '🚫 Доступ запрещен. Извините.')
                    return

                safe_api_call(current_bot.reply_to, message, '🗣️ Запишите голосовое сообщение, либо перешлите его мне.')

            @current_bot.message_handler(content_types=['voice'])
            def voice_processing(message):
                """Обработка голосовых сообщений"""
                if not bot_running:
                    return
                    
                if message.from_user.id != ALLOWED_USER_ID:
                    safe_api_call(current_bot.reply_to, message, '🚫 Доступ запрещен. Извините.')
                    return

                # Обрабатываем в отдельном потоке чтобы не блокировать polling
                threading.Thread(target=process_voice_in_thread, args=(current_bot, message), daemon=True).start()

            def process_voice_in_thread(bot, message):
                """Обработка голосового сообщения в отдельном потоке"""
                if not bot_running:
                    return
                    
                ogg_filepath = None
                wav_filepath = None
                
                try:
                    safe_api_call(bot.reply_to, message, '⌛ Подождите немного, я обрабатываю голосовое сообщение...')

                    if not bot_running:
                        return
                        
                    file_id = message.voice.file_id
                    file_info = safe_api_call(bot.get_file, file_id)
                    
                    if not bot_running or not file_info:
                        return
                        
                    downloaded_file = safe_api_call(bot.download_file, file_info.file_path)
                    
                    if not bot_running or not downloaded_file:
                        return
                    
                    # Уникальные имена файлов
                    timestamp = int(time.time())
                    ogg_filepath = os.path.join(TEMP_AUDIO_DIR, f'audio_{timestamp}.ogg')
                    wav_filepath = os.path.join(TEMP_AUDIO_DIR, f'audio_{timestamp}.wav')

                    with open(ogg_filepath, 'wb') as new_file:
                        new_file.write(downloaded_file)

                    if not bot_running:
                        return

                    # Конвертация с таймаутом
                    result = subprocess.run([
                        'ffmpeg',
                        '-i', ogg_filepath,
                        '-acodec', 'pcm_s16le',
                        '-ar', '44100',
                        '-y',
                        wav_filepath
                    ], capture_output=True, timeout=120)
                    
                    if result.returncode != 0:
                        raise Exception(f"Ошибка конвертации: {result.stderr.decode()}")

                    if not bot_running:
                        return

                    chunk_paths = split_audio_file(wav_filepath)
                    if chunk_paths and bot_running:
                        process_recognition(bot, message, chunk_paths)
                    elif bot_running:
                        safe_api_call(bot.reply_to, message, '⚠️ Не удалось обработать аудио файл.')

                except subprocess.TimeoutExpired:
                    if bot_running:
                        safe_api_call(bot.reply_to, message, '⚠️ Превышено время обработки файла.')
                    logger.error("Таймаут при конвертации")
                except Exception as e:
                    if bot_running:
                        safe_api_call(bot.reply_to, message, f'⚠️ Ошибка при подготовке: {str(e)}')
                    logger.error(f"Ошибка обработки голосового сообщения: {e}")
                finally:
                    # Удаляем временные файлы
                    for filepath in [ogg_filepath, wav_filepath]:
                        if filepath and os.path.exists(filepath):
                            try:
                                os.remove(filepath)
                            except Exception as e:
                                logger.warning(f"Не удалось удалить {filepath}: {e}")

            def process_recognition(bot, message, chunk_paths):
                """Распознавание речи с улучшенной обработкой"""
                if not bot_running:
                    return
                    
                recognizer = sr.Recognizer()
                # Настройки для лучшего распознавания
                recognizer.energy_threshold = 300
                recognizer.dynamic_energy_threshold = True

                try:
                    safe_api_call(bot.send_message, message.chat.id, '📝 Начинаю распознавание...')

                    recognized_texts = []
                    for i, chunk_path in enumerate(chunk_paths, 1):
                        if not bot_running:
                            break
                            
                        try:
                            with sr.AudioFile(chunk_path) as source:
                                # Настройка для устранения шума
                                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                                audio_data = recognizer.record(source)
                                
                                chunk_text = recognizer.recognize_google(audio_data, language='ru-RU')
                                if chunk_text.strip():
                                    recognized_texts.append(chunk_text)
                                    if bot_running:
                                        safe_api_call(bot.send_message, message.chat.id, f"Часть {i}: {chunk_text}")
                                    
                        except sr.UnknownValueError:
                            if bot_running:
                                safe_api_call(bot.send_message, message.chat.id, f'⚠️ Часть {i}: не распознана.')
                        except sr.RequestError as e:
                            if bot_running:
                                safe_api_call(bot.send_message, message.chat.id, f'⚠️ Часть {i}: ошибка сервиса.')
                            logger.error(f"Ошибка сервиса распознавания: {e}")
                        except Exception as e:
                            if bot_running:
                                safe_api_call(bot.send_message, message.chat.id, f'⚠️ Часть {i}: ошибка обработки.')
                            logger.error(f"Ошибка распознавания части {i}: {e}")
                        finally:
                            # Удаляем обработанный чанк
                            try:
                                if os.path.exists(chunk_path):
                                    os.remove(chunk_path)
                            except Exception as e:
                                logger.warning(f"Не удалось удалить чанк {chunk_path}: {e}")

                    # Итоговый результат
                    if bot_running:
                        if recognized_texts:
                            full_text = " ".join(recognized_texts)
                            safe_api_call(bot.send_message, message.chat.id, f'📄 Полный текст:\n\n{full_text}')
                        else:
                            safe_api_call(bot.send_message, message.chat.id, '😔 Речь не распознана.')
                        
                        safe_api_call(bot.send_message, message.chat.id, '✅ Готово!')

                except Exception as e:
                    if bot_running:
                        safe_api_call(bot.send_message, message.chat.id, f'⚠️ Ошибка распознавания: {str(e)}')
                    logger.error(f"Общая ошибка распознавания: {e}")

            # Запуск бота с polling в цикле для возможности прерывания
            logger.info("Бот запущен и готов к работе!")
            restart_count = 0  # Сброс при успешном запуске
            
            # Используем обычный polling в цикле вместо infinity_polling
            while bot_running:
                try:
                    current_bot.polling(
                        timeout=10,
                        long_polling_timeout=5,
                        logger_level=logging.WARNING,
                        none_stop=False,
                        allowed_updates=['message']
                    )
                except Exception as e:
                    if bot_running:
                        logger.warning(f"Ошибка в polling: {e}")
                        time.sleep(2)
                    else:
                        break
            
        except (ReadTimeout, ConnectionError) as e:
            if bot_running:
                restart_count += 1
                wait_time = min(15 * restart_count, 120)  # Максимум 2 минуты
                logger.warning(f"Ошибка соединения: {e}. Перезапуск через {wait_time}с...")
                time.sleep(wait_time)
            else:
                break
                
        except KeyboardInterrupt:
            logger.info("Прерывание от пользователя")
            bot_running = False
            break
            
        except Exception as e:
            if bot_running:
                restart_count += 1
                logger.error(f"Неожиданная ошибка: {e}")
                if restart_count < max_restarts:
                    wait_time = min(10 * restart_count, 60)
                    logger.info(f"Перезапуск через {wait_time}с...")
                    time.sleep(wait_time)
                else:
                    break
            else:
                break
                
        finally:
            if current_bot:
                try:
                    current_bot.stop_polling()
                    logger.info("Polling окончательно остановлен")
                except:
                    pass

    if restart_count >= max_restarts:
        logger.error(f"Превышено максимальное количество перезапусков ({max_restarts})")
    
    cleanup_temp_files()
    logger.info("Бот завершил работу")

if __name__ == '__main__':
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Работа бота прервана")
    finally:
        cleanup_temp_files()
        logger.info("Программа завершена")
