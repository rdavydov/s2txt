import telebot
import speech_recognition as sr
import os
import numpy as np
import subprocess
import time
import logging
from telebot.handler_backends import State
from requests.exceptions import ReadTimeout, ConnectionError

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

# Получение токена и ID пользователя из переменных окружения
TOKEN = os.getenv('TOKEN')
ALLOWED_USER_ID = os.getenv('ALLOWED_USER_ID')

# Если переменные окружения не установлены, пытаемся импортировать из конфига
if not TOKEN or not ALLOWED_USER_ID:
    from config import TOKEN, ALLOWED_USER_ID

# Создание директории для временных аудиофайлов
TEMP_AUDIO_DIR = 'temp_audio'
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)


def run_bot():
    """
    Основная функция запуска и работы бота.
    Включает в себя механизмы обработки ошибок и автоматического перезапуска.
    """
    bot = telebot.TeleBot(token=TOKEN)

    def split_audio_file(input_file, chunk_duration=30):
        """
        Разбивает аудиофайл на части указанной длительности для облегчения распознавания.

        Args:
            input_file (str): Путь к входному аудиофайлу
            chunk_duration (int): Длительность каждого куска в секундах

        Returns:
            list: Список путей к созданным аудио-чанкам
        """
        # Получаем длительность входного файла
        audio_duration = float(subprocess.check_output([
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            input_file
        ]).decode().strip())

        chunk_paths = []
        # Разбиваем файл на куски указанной длительности
        for start in np.arange(0, audio_duration, chunk_duration):
            end = min(start + chunk_duration, audio_duration)
            chunk_filename = os.path.join(
                TEMP_AUDIO_DIR,
                f'audio_chunk_{int(start)}.wav'
            )

            # Используем ffmpeg для создания куска аудио
            subprocess.run([
                'ffmpeg',
                '-i', input_file,
                '-ss', str(start),
                '-to', str(end),
                '-acodec', 'pcm_s16le',
                '-ar', '44100',
                chunk_filename
            ], check=True, capture_output=True)

            chunk_paths.append(chunk_filename)

        return chunk_paths

    @bot.message_handler()
    def text_processing(message):
        """
        Обработчик текстовых сообщений.
        Проверяет доступ пользователя и отправляет инструкции.

        Args:
            message (telebot.types.Message): Входящее сообщение
        """
        # Проверка доступа пользователя
        if message.from_user.id != ALLOWED_USER_ID:
            bot.reply_to(message, '🚫 Доступ запрещен. Извините.')
            return

        bot.reply_to(
            message, '🗣️ Запишите голосовое сообщение, либо перешлите его мне.')

    @bot.message_handler(content_types=['voice'])
    def voice_processing(message):
        """
        Обработчик голосовых сообщений.
        Скачивает голосовое сообщение и подготавливает его к распознаванию.

        Args:
            message (telebot.types.Message): Входящее голосовое сообщение
        """
        # Проверка доступа пользователя
        if message.from_user.id != ALLOWED_USER_ID:
            bot.reply_to(message, '🚫 Доступ запрещен. Извините.')
            return

        if message:
            bot.reply_to(
                message, '⌛ Подождите немного, я обрабатываю голосовое сообщение...')

            # Получение и скачивание файла
            file_id = message.voice.file_id
            file = bot.get_file(file_id)
            file_path = file.file_path

            downloaded_file = bot.download_file(file_path)
            ogg_filepath = os.path.join(TEMP_AUDIO_DIR, 'audio.ogg')
            wav_filepath = os.path.join(TEMP_AUDIO_DIR, 'audio.wav')

            # Сохранение скачанного файла
            with open(ogg_filepath, 'wb') as new_file:
                new_file.write(downloaded_file)

            try:
                # Конвертация из OGG в WAV
                subprocess.run([
                    'ffmpeg',
                    '-i', ogg_filepath,
                    '-acodec', 'pcm_s16le',
                    '-ar', '44100',
                    wav_filepath
                ], check=True, capture_output=True)

                # Разбиение на части и распознавание
                chunk_paths = split_audio_file(wav_filepath)
                process_recognition(message, chunk_paths)

            except Exception as e:
                bot.reply_to(
                    message, f'⚠️ Извините, произошла ошибка при подготовке: {str(e)}')
                logger.error(f"Ошибка при обработке голосового сообщения: {e}")
            finally:
                # Очистка временных файлов
                try:
                    os.remove(ogg_filepath)
                    os.remove(wav_filepath)
                except Exception as e:
                    logger.warning(f"Не удалось удалить временные файлы: {e}")

        else:
            bot.reply_to(
                message, '🤔 Пересланных голосовых сообщений не найдено.')

    def process_recognition(message, chunk_paths):
        """
        Выполняет распознавание речи для каждого куска аудио.

        Args:
            message (telebot.types.Message): Исходное сообщение для ответа
            chunk_paths (list): Список путей к аудио-чанкам
        """
        recognizer = sr.Recognizer()

        try:
            bot.send_message(message.chat.id, '📝')

            # Обработка каждого куска аудио
            for i, chunk_path in enumerate(chunk_paths, 1):
                try:
                    with sr.AudioFile(chunk_path) as source:
                        audio_data = recognizer.record(source)
                        # Распознавание речи с помощью Google Speech Recognition
                        chunk_text = recognizer.recognize_google(
                            audio_data, language='ru-RU')
                        bot.send_message(message.chat.id, chunk_text)
                except sr.UnknownValueError:
                    bot.send_message(
                        message.chat.id, f'⚠️ Часть {i}: не распознана.')
                except Exception as e:
                    bot.send_message(
                        message.chat.id, f'⚠️ Часть {i}: ошибка распознавания.')
                    logger.error(f"Ошибка при распознавании части {i}: {e}")
                finally:
                    # Очистка временных файлов
                    try:
                        os.remove(chunk_path)
                    except Exception as e:
                        logger.warning(
                            f"Не удалось удалить чанк {chunk_path}: {e}")

            bot.send_message(message.chat.id, '🔚')

        except Exception as e:
            bot.send_message(
                message.chat.id,
                f'⚠️ Извините, произошла ошибка при распознавании: {str(e)}'
            )
            logger.error(f"Общая ошибка при распознавании: {e}")

    # Основной цикл работы бота с обработкой ошибок
    while True:
        try:
            logger.info("Запуск бота...")
            # Запуск бота с увеличенными таймаутами
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=70)
        except ReadTimeout as e:
            logger.warning(f"Превышено время ожидания: {e}")
            time.sleep(15)  # Пауза перед повторным подключением
        except ConnectionError as e:
            logger.error(f"Ошибка подключения: {e}")
            # Более длительная пауза при проблемах с соединением
            time.sleep(30)
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            time.sleep(10)
        finally:
            try:
                # Корректное завершение сессии бота
                bot.stop_polling()
            except Exception as e:
                logger.error(f"Ошибка при остановке polling: {e}")

            logger.info("Перезапуск бота через 10 секунд...")
            time.sleep(10)


if __name__ == '__main__':
    run_bot()
