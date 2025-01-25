
## 🤖 Конвертер голосовых сообщений Telegram
Бесплатный Телеграм-Бот, который конвертирует голосовые сообщения в текст.
Бот на русском языке. Находится в процессе доработки и добавления нового функционала.
Минимализм бота устроит тех, кому не хочется покупать Telegram Premium и нет сил слушать длинные голосовые сообщения.

## Лицензия

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)

## Код основан на

- https://gitverse.ru/vv800180/VoiceTelegramBot
- https://gitverse.ru/pankovea/VoiceTelegramBot

## Дополнение

Для запуска :
1. Создайте файл config.py
2. Вставьте в него следующую строку: ```TOKEN = 'your_token_here'```, замените your_token_here на ваш токен.
3. Вставьте в него следующую строку: ```ALLOWED_USER_ID = 'your_user_id_here'```, замените your_user_id_here на ваш Telegram User ID (можно узнать у @getmyid_bot).

Для запуска в контейнере Docker:
1. Создайте файл .env
2. Вставьте в него следующую строку: ```TOKEN=your_token_here```, замените your_token_here на ваш токен.
3. Вставьте в него следующую строку: ```ALLOWED_USER_ID = 'your_user_id_here'```, замените your_user_id_here на ваш Telegram User ID (можно узнать у @getmyid_bot).
4. ```docker compose -f "docker-compose.yml" up -d --build```
