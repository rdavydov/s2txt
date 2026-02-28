
## 🤖 Конвертер голосовых сообщений Telegram
Бесплатный Телеграм-Бот, который конвертирует голосовые сообщения, видео-кружки и обычные видео в текст.
Бот на русском языке. Находится в процессе доработки и добавления нового функционала.
Минимализм бота устроит тех, кому не хочется покупать Telegram Premium и нет сил слушать длинные голосовые сообщения.

## Поддерживаемые типы сообщений

- 🗣️ Голосовые сообщения (`voice`)
- 🟣 Видео-кружки (`video_note`)
- 🎥 Обычные видео (`video`)

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

## 🚀 **Дополнительные рекомендации:**

Для еще большей стабильности создайте systemd service:

```bash
# Создайте файл /etc/systemd/system/telegram-bot.service
sudo nano /etc/systemd/system/telegram-bot.service
```

```ini
[Unit]
Description=Telegram Voice Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/VoiceTelegramBot
Environment=PYTHONPATH=/root/VoiceTelegramBot
ExecStart=/root/VoiceTelegramBot/venv-python38/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Затем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

Теперь бот должен работать стабильно 24/7 без ручных перезапусков!
