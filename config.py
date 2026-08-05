import os

# Токен бота — получить у @BotFather в Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Твой Telegram user id — бот будет отвечать только тебе (защита от чужих сообщений)
# Узнать свой id можно у бота @userinfobot
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Путь к файлу базы данных SQLite
DB_PATH = os.environ.get("DB_PATH", "fishing.db")

# --- Хранилище фото приманок (опционально, можно оставить пустым) ---
# Фото загружаются в GitHub-репозиторий как в бесплатное постоянное хранилище.
# Как настроить:
#  1. Создай GitHub-репозиторий (можно приватный), например "fishing-photos".
#  2. Создай токен: GitHub -> Settings -> Developer settings -> Personal access tokens
#     (Fine-grained token, доступ Contents: Read and write только для этого репозитория).
#  3. Впиши переменные окружения ниже.
# Если оставить пустым — бот просто не будет предлагать прикреплять фото.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # формат "username/repo-name"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

PHOTOS_ENABLED = bool(GITHUB_TOKEN and GITHUB_REPO)

# Порог похожести названий для проверки на дубли (0..1, чем выше — тем строже)
FUZZY_THRESHOLD = 0.72

# Сколько последних вариантов показывать кнопками (приманки/водоёмы/места)
RECENT_LIMIT = 20

# --- Веб-API для дашборда ---
# Дашборд (HTML-файл) обращается к этому адресу бота, чтобы получить свежие
# данные вместо разовой выгрузки. API_TOKEN — простая защита, чтобы данные
# не были доступны кому попало по прямой ссылке (это не банковский уровень
# защиты, но для личного проекта достаточно — придумай любую случайную строку).
API_TOKEN = os.environ.get("API_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))
