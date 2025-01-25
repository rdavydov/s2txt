import telebot
import speech_recognition as sr
import os
import numpy as np
import subprocess

TOKEN = os.getenv('TOKEN')
if not TOKEN:
    from config import TOKEN, ALLOWED_USER_ID

bot = telebot.TeleBot(token=TOKEN)

TEMP_AUDIO_DIR = 'temp_audio'
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)


def split_audio_file(input_file, chunk_duration=30):
    audio_duration = float(subprocess.check_output([
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        input_file
    ]).decode().strip())

    chunk_paths = []
    for start in np.arange(0, audio_duration, chunk_duration):
        end = min(start + chunk_duration, audio_duration)
        chunk_filename = os.path.join(
            TEMP_AUDIO_DIR,
            f'audio_chunk_{int(start)}.wav'
        )

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
    if message.from_user.id != ALLOWED_USER_ID:
        bot.reply_to(message, '🚫 Доступ запрещен. Извините.')
        return

    bot.reply_to(
        message, '🗣️ Запишите голосовое сообщение, либо перешлите его мне.')


@bot.message_handler(content_types=['voice'])
def voice_processing(message):
    # Check user access
    if message.from_user.id != ALLOWED_USER_ID:
        bot.reply_to(message, '🚫 Доступ запрещен. Извините.')
        return

    if message:
        bot.reply_to(
            message, '⌛ Подождите немного, я обрабатываю голосовое сообщение...')

        file_id = message.voice.file_id
        file = bot.get_file(file_id)
        file_path = file.file_path

        downloaded_file = bot.download_file(file_path)
        ogg_filepath = os.path.join(
            TEMP_AUDIO_DIR,
            'audio.ogg'
        )
        wav_filepath = os.path.join(
            TEMP_AUDIO_DIR,
            'audio.wav'
        )

        with open(ogg_filepath, 'wb') as new_file:
            new_file.write(downloaded_file)

        try:
            subprocess.run([
                'ffmpeg',
                '-i', ogg_filepath,
                '-acodec', 'pcm_s16le',
                '-ar', '44100',
                wav_filepath
            ], check=True, capture_output=True)

            chunk_paths = split_audio_file(wav_filepath)
            process_recognition(message, chunk_paths)

        except Exception as e:
            bot.reply_to(
                message, f'⚠️ Извините, произошла ошибка при подготовке: {str(e)}')
        finally:
            try:
                os.remove(ogg_filepath)
                os.remove(wav_filepath)
            except Exception:
                pass

    else:
        bot.reply_to(message, '🤔 Пересланных голосовых сообщений не найдено.')


def process_recognition(message, chunk_paths):
    recognizer = sr.Recognizer()

    try:
        bot.send_message(message.chat.id, '📝')

        for i, chunk_path in enumerate(chunk_paths, 1):
            try:
                with sr.AudioFile(chunk_path) as source:
                    audio_data = recognizer.record(source)
                    chunk_text = recognizer.recognize_google(
                        audio_data, language='ru-RU')
                    bot.send_message(message.chat.id, chunk_text)
            except sr.UnknownValueError:
                bot.send_message(
                    message.chat.id, f'⚠️ Часть {i}: не распознана.')
            except Exception:
                bot.send_message(
                    message.chat.id, f'⚠️ Часть {i}: ошибка распознавания.')
            finally:
                try:
                    os.remove(chunk_path)
                except Exception:
                    pass

        bot.send_message(message.chat.id, '🔚')

    except Exception as e:
        bot.send_message(
            message.chat.id,
            f'⚠️ Извините, произошла ошибка при распознавании: {str(e)}'
        )


if __name__ == '__main__':
    bot.polling(none_stop=True)
