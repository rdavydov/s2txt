import telebot
import speech_recognition as sr
import os
import numpy as np
import subprocess
import time
import logging
from tqdm import tqdm
from datetime import datetime
from telebot.handler_backends import State
from requests.exceptions import ReadTimeout, ConnectionError
from config import *
from metrics import MetricsCollector, measure_time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(
            PATHS['logs'], f'bot_{datetime.now().strftime("%Y%m%d")}.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация сборщика метрик
metrics_collector = MetricsCollector(PATHS['metrics'])


def run_bot():
    """Основная функция запуска и работы бота."""
    bot = telebot.TeleBot(token=TOKEN)

    @measure_time(metrics_collector, 'audio_splitting')
    def split_audio_file(input_file, chunk_duration=AUDIO_SETTINGS['chunk_duration']):
        """
        Разбивает аудиофайл на части с отображением прогресса.

        Args:
            input_file (str): Путь к входному аудиофайлу
            chunk_duration (int): Длительность каждого куска в секундах

        Returns:
            list: Список путей к созданным аудио-чанкам
        """
        logger.info(f"Начало разбиения файла: {input_file}")

        # Получение длительности файла
        audio_duration = float(subprocess.check_output([
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            input_file
        ]).decode().strip())

        chunk_paths = []
        chunks = np.arange(0, audio_duration, chunk_duration)

        # Прогресс-бар для разбиения файла
        with tqdm(total=len(chunks), desc="Разбиение аудио", unit="chunk") as pbar:
            for start in chunks:
                end = min(start + chunk_duration, audio_duration)
                chunk_filename = os.path.join(
                    PATHS['temp_audio'],
                    f'audio_chunk_{int(start)}.wav'
                )

                subprocess.run([
                    'ffmpeg',
                    '-i', input_file,
                    '-ss', str(start),
                    '-to', str(end),
                    '-acodec', AUDIO_SETTINGS['audio_codec'],
                    '-ar', str(AUDIO_SETTINGS['sample_rate']),
                    chunk_filename
                ], check=True, capture_output=True)

                chunk_paths.append(chunk_filename)
                pbar.update(1)
                logger.debug(f"Создан чанк: {chunk_filename}")

        logger.info(f"Файл успешно разбит на {len(chunk_paths)} частей")
        return chunk_paths

    @bot.message_handler()
    def text_processing(message):
        """
        Обработчик текстовых сообщений.

        Args:
            message (telebot.types.Message): Входящее сообщение
        """
        if message.from_user.id != ALLOWED_USER_ID:
            logger.warning(
                f"Попытка неавторизованного доступа от пользователя {message.from_user.id}")
            bot.reply_to(message, '🚫 Доступ запрещен. Извините.')
            return

        logger.info(
            f"Получено текстовое сообщение от пользователя {message.from_user.id}")
        bot.reply_to(
            message, '🗣️ Запишите голосовое сообщение, либо перешлите его мне.')

    @bot.message_handler(content_types=['voice'])
    @measure_time(metrics_collector, 'voice_processing')
    def voice_processing(message):
        """
        Обработчик голосовых сообщений с отображением прогресса.

        Args:
            message (telebot.types.Message): Входящее голосовое сообщение
        """
        if message.from_user.id != ALLOWED_USER_ID:
            logger.warning(
                f"Попытка неавторизованного доступа от пользователя {message.from_user.id}")
            bot.reply_to(message, '🚫 Доступ запрещен. Извините.')
            return

        if message:
            logger.info(
                f"Начало обработки голосового сообщения от пользователя {message.from_user.id}")
            bot.reply_to(
                message, '⌛ Подождите немного, я обрабатываю голосовое сообщение...')

            # Прогресс-бар для скачивания и конвертации
            with tqdm(total=3, desc="Подготовка аудио", unit="step") as pbar:
                try:
                    # Шаг 1: Получение файла
                    file_id = message.voice.file_id
                    file = bot.get_file(file_id)
                    file_path = file.file_path
                    downloaded_file = bot.download_file(file_path)
                    pbar.update(1)
                    logger.debug("Файл успешно скачан")

                    # Шаг 2: Сохранение OGG
                    ogg_filepath = os.path.join(
                        PATHS['temp_audio'], 'audio.ogg')
                    wav_filepath = os.path.join(
                        PATHS['temp_audio'], 'audio.wav')
                    with open(ogg_filepath, 'wb') as new_file:
                        new_file.write(downloaded_file)
                    pbar.update(1)
                    logger.debug("OGG файл сохранен")

                    # Шаг 3: Конвертация в WAV
                    subprocess.run([
                        'ffmpeg',
                        '-i', ogg_filepath,
                        '-acodec', AUDIO_SETTINGS['audio_codec'],
                        '-ar', str(AUDIO_SETTINGS['sample_rate']),
                        wav_filepath
                    ], check=True, capture_output=True)
                    pbar.update(1)
                    logger.debug("Конвертация в WAV завершена")

                    # Разбиение на части и распознавание
                    chunk_paths = split_audio_file(wav_filepath)
                    process_recognition(message, chunk_paths)

                except Exception as e:
                    logger.error(
                        f"Ошибка при обработке голосового сообщения: {str(e)}")
                    bot.reply_to(
                        message, f'⚠️ Извините, произошла ошибка при подготовке: {str(e)}')
                finally:
                    # Очистка временных файлов
                    for filepath in [ogg_filepath, wav_filepath]:
                        try:
                            if os.path.exists(filepath):
                                os.remove(filepath)
                                logger.debug(
                                    f"Удален временный файл: {filepath}")
                        except Exception as e:
                            logger.warning(
                                f"Не удалось удалить временный файл {filepath}: {str(e)}")

        else:
            logger.warning("Получено пустое голосовое сообщение")
            bot.reply_to(
                message, '🤔 Пересланных голосовых сообщений не найдено.')

    @measure_time(metrics_collector, 'speech_recognition')
    def process_recognition(message, chunk_paths):
        """
        Выполняет распознавание речи с отображением прогресса.

        Args:
            message (telebot.types.Message): Исходное сообщение для ответа
            chunk_paths (list): Список путей к аудио-чанкам
        """
        recognizer = sr.Recognizer()
        logger.info(f"Начало распознавания {len(chunk_paths)} частей аудио")

        try:
            bot.send_message(message.chat.id, '📝')

            # Прогресс-бар для распознавания
            with tqdm(total=len(chunk_paths), desc="Распознавание речи", unit="chunk") as pbar:
                for i, chunk_path in enumerate(chunk_paths, 1):
                    try:
                        with sr.AudioFile(chunk_path) as source:
                            audio_data = recognizer.record(source)
                            chunk_text = recognizer.recognize_google(
                                audio_data, language=BOT_SETTINGS['language'])
                            bot.send_message(message.chat.id, chunk_text)
                            logger.debug(f"Успешно распознана часть {i}")
                    except sr.UnknownValueError:
                        logger.warning(f"Не удалось распознать часть {i}")
                        bot.send_message(
                            message.chat.id, f'⚠️ Часть {i}: не распознана.')
                    except Exception as e:
                        logger.error(
                            f"Ошибка при распознавании части {i}: {str(e)}")
                        bot.send_message(
                            message.chat.id, f'⚠️ Часть {i}: ошибка распознавания.')
                    finally:
                        try:
                            if os.path.exists(chunk_path):
                                os.remove(chunk_path)
                                logger.debug(
                                    f"Удален временный файл чанка: {chunk_path}")
                        except Exception as e:
                            logger.warning(
                                f"Не удалось удалить чанк {chunk_path}: {str(e)}")
                        pbar.update(1)

            bot.send_message(message.chat.id, '🔚')
            logger.info("Распознавание успешно завершено")

        except Exception as e:
            logger.error(f"Общая ошибка при распознавании: {str(e)}")
            bot.send_message(
                message.chat.id,
                f'⚠️ Извините, произошла ошибка при распознавании: {str(e)}'
            )

    # Основной цикл работы бота
    while True:
        try:
            logger.info("Запуск бота...")
            bot.polling(
                none_stop=True,
                timeout=BOT_SETTINGS['timeout'],
                long_polling_timeout=BOT_SETTINGS['long_polling_timeout']
            )
        except ReadTimeout as e:
            logger.warning(f"Превышено время ожидания: {str(e)}")
            time.sleep(BOT_SETTINGS['reconnect_delay'])
        except ConnectionError as e:
            logger.error(f"Ошибка подключения: {str(e)}")
            time.sleep(BOT_SETTINGS['reconnect_delay'] * 2)
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {str(e)}")
            time.sleep(BOT_SETTINGS['reconnect_delay'])
        finally:
            try:
                bot.stop_polling()
            except Exception as e:
                logger.error(f"Ошибка при остановке polling: {str(e)}")

            # Вывод текущих метрик перед перезапуском
            metrics_summary = metrics_collector.get_metrics_summary()
            logger.info("Текущие метрики производительности:")
            for operation, stats in metrics_summary.items():
                logger.info(f"{operation}: среднее время - {stats['average_time']}с, "
                            f"всего операций - {stats['total_operations']}")

            logger.info("Перезапуск бота через 10 секунд...")
            time.sleep(10)


if __name__ == '__main__':
    logger.info("Инициализация бота...")
    run_bot()
