
## 🤖 Конвертер голосовых сообщений Telegram
Бесплатный Телеграм-Бот, который конвертирует голосовые сообщения в текст.
Бот на русском языке. Находится в процессе доработки и добавления нового функционала.
Минимализм бота устроит тех, кому не хочется покупать Telegram Premium и нет сил слушать длинные голосовые сообщения.

## Лицензия

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)

## Код основан на

- https://gitverse.ru/vv800180/VoiceTelegramBot
- https://gitverse.ru/pankovea/VoiceTelegramBot

## Системные требования

- Python 3.8 или выше
- ffmpeg
- Доступ к интернету
- Токен Telegram бота
- Достаточно места на диске для временных аудиофайлов

## Установка зависимостей

### 1. Установка системных зависимостей

Для Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg python3-pip python3-venv
```

Для CentOS/RHEL:
```bash
sudo yum install -y ffmpeg python3-pip python3-venv
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # для Linux/Mac
# или
venv\Scripts\activate  # для Windows
```

### 3. Установка Python-зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Настройка

1. Создайте копию файла конфигурации:
```bash
cp config.py.example config.py
```

2. Отредактируйте `config.py`:
- Укажите ваш TOKEN от BotFather
- Укажите ваш ALLOWED_USER_ID (ID пользователя Telegram)
- При необходимости измените другие параметры

## Запуск

### Обычный запуск

```bash
python main.py
```

### Запуск в tmux (рекомендуется для серверов)

```bash
tmux new-session -d -s voice_bot 'python main.py'
```

Подключение к сессии:
```bash
tmux attach -t voice_bot
```

Отключение от сессии (без остановки бота): `Ctrl+B`, затем `D`

## Мониторинг

### Логи

Логи сохраняются в директории `logs/`. Текущий лог: `bot_YYYYMMDD.log`

Просмотр логов в реальном времени:
```bash
tail -f logs/bot_*.log
```

### Метрики

Метрики производительности сохраняются в `metrics/performance_metrics.json`

Просмотр метрик:
```bash
cat metrics/performance_metrics.json
```

## Устранение неполадок

### Проблемы с распознаванием речи

1. Проверьте наличие доступа к интернету
2. Убедитесь, что ffmpeg установлен корректно:
```bash
ffmpeg -version
```

### Проблемы с Telegram API

1. Проверьте правильность токена
2. Убедитесь, что бот не заблокирован пользователем
3. Проверьте доступ к api.telegram.org

### Очистка временных файлов

Если бот был некорректно остановлен, могут остаться временные файлы:
```bash
rm -rf temp_audio/*
```

## Обновление

1. Остановите бота (Ctrl+C или `tmux kill-session -t voice_bot`)
2. Получите последние изменения
3. Обновите зависимости:
```bash
pip install -r requirements.txt --upgrade
```
4. Перезапустите бота

## Безопасность

- Храните `config.py` в безопасном месте
- Регулярно обновляйте зависимости
- Используйте брандмауэр для ограничения доступа
- Настройте правильные разрешения для файлов:
```bash
chmod 600 config.py
chmod 700 venv/
```

## Docker

Для запуска в контейнере Docker:
1. Создайте файл .env
2. Вставьте в него следующую строку: ```TOKEN=your_token_here```, замените your_token_here на ваш токен.
3. Вставьте в него следующую строку: ```ALLOWED_USER_ID = 'your_user_id_here'```, замените your_user_id_here на ваш Telegram User ID (можно узнать у @getmyid_bot).
4. При необходимости измените другие параметры.
5. ```docker compose -f "docker-compose.yml" up -d --build```
