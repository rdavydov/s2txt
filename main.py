import telebot
from moviepy.editor import AudioFileClip
import speech_recognition as sr
import os
import wave
import numpy as np

TOKEN = os.getenv('TOKEN')
if not TOKEN:
    from config import TOKEN
    
bot = telebot.TeleBot(token=TOKEN)


# приветственное сообщение
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
                 f'Привет, {message.chat.first_name}! Я бот, который умеет конвертировать голосовые сообщения в текст.\nЧтобы начать, просто перешли мне голосовое сообщение.')


# вывод возможностей бота после нажатия на кнопку "старт"
@bot.message_handler(commands=['help'])
def bot_capabilities(message):
    bot.reply_to(message, 'Я могу конвертировать голосовые сообщения в текст.\nПросто перешли мне голосовое сообщение, которое ты слушать не хочешь!')


# функция, которая будет вызываться при получении голосового сообщения
def split_audio_file(input_file, chunk_duration=30):
    """
    Split an audio file into chunks of specified duration.
    
    :param input_file: Path to input audio file
    :param chunk_duration: Duration of each chunk in seconds
    :return: List of chunk file paths
    """
    # Load the audio file
    audio = AudioFileClip(input_file)
    total_duration = audio.duration
    chunk_paths = []

    # Calculate chunk parameters
    sample_width = 2  # 16-bit audio
    channels = 2      # stereo
    sample_rate = 44100  # standard sample rate

    for start in np.arange(0, total_duration, chunk_duration):
        end = min(start + chunk_duration, total_duration)
        chunk = audio.subclip(start, end)
        
        # Generate unique chunk filename
        chunk_filename = f'audio_chunk_{int(start)}.wav'
        chunk.write_audiofile(chunk_filename, codec='pcm_s16le')
        chunk_paths.append(chunk_filename)

    return chunk_paths

def recognize_audio_chunks(chunk_paths, language='ru-RU'):
    """
    Recognize text from audio chunks.
    
    :param chunk_paths: List of audio chunk file paths
    :param language: Language for speech recognition
    :return: Full recognized text
    """
    recognizer = sr.Recognizer()
    full_text = []

    for chunk_path in chunk_paths:
        try:
            with sr.AudioFile(chunk_path) as source:
                audio_data = recognizer.record(source)
                chunk_text = recognizer.recognize_google(audio_data, language=language)
                full_text.append(chunk_text)
        except sr.UnknownValueError:
            full_text.append(f'[Chunk {chunk_path} could not be recognized]')
        except Exception as e:
            full_text.append(f'[Error processing {chunk_path}: {str(e)}]')
        
        # Clean up temporary chunk file
        os.remove(chunk_path)

    return ' '.join(full_text)

def send_long_message(bot, chat_id, text, max_length=4096):
    """
    Send a long message by splitting it into chunks.
    
    :param bot: Telegram Bot instance
    :param chat_id: Chat ID to send message to
    :param text: Full text message
    :param max_length: Maximum length of a single message
    """
    # Split text into chunks
    chunks = []
    while len(text) > max_length:
        # Find the last space before max_length to avoid cutting words
        split_index = text[:max_length].rfind(' ')
        if split_index == -1:
            split_index = max_length
        
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    
    # Add the last chunk
    if text:
        chunks.append(text)
    
    # Send each chunk
    for chunk in chunks:
        bot.send_message(chat_id, chunk)

# Modify the voice_processing function to use this
@bot.message_handler(content_types=['voice'])
def voice_processing(message):
    if message:
        bot.reply_to(message, 'Подождите немного, я обрабатываю голосовое сообщение :)')

        file_id = message.voice.file_id
        file = bot.get_file(file_id)
        file_path = file.file_path

        # Download and save Telegram voice message
        downloaded_file = bot.download_file(file_path)
        with open('audio.ogg', 'wb') as new_file:
            new_file.write(downloaded_file)

        # Convert to WAV
        audio = AudioFileClip('audio.ogg')
        audio.write_audiofile('audio.wav')

        try:
            # Split audio into chunks and recognize
            chunk_paths = split_audio_file('audio.wav')
            text = recognize_audio_chunks(chunk_paths)
            
            # Send long message in chunks
            send_long_message(bot, message.chat.id, text)
        except Exception as e:
            bot.reply_to(message, f'Извините, произошла ошибка при распознавании: {str(e)}')
        finally:
            # Clean up original files
            os.remove('audio.ogg')
            os.remove('audio.wav')
    else:
        bot.reply_to(message, 'Пересланных голосовых сообщений не найдено')

if __name__ == '__main__':
    bot.polling(none_stop=True)
