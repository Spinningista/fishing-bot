"""
Хранилище фото приманок.

Фото приманок нужно где-то хранить постоянно (бесплатный хостинг бота обычно
не сохраняет файлы между перезапусками). Проще всего — публичный/приватный
GitHub-репозиторий: бесплатно, надёжно, даёт постоянную прямую ссылку на файл.

Если GITHUB_TOKEN / GITHUB_REPO не заданы в config.py — функции просто
возвращают None, и бот работает без фото.
"""
import base64
import time
import requests

from config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, PHOTOS_ENABLED


def upload_photo(file_bytes: bytes, filename: str) -> str | None:
    """Загружает фото в GitHub-репозиторий, возвращает публичную ссылку (raw URL) или None."""
    if not PHOTOS_ENABLED:
        return None

    path = f"lure_photos/{filename}"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "message": f"Добавлено фото приманки: {filename}",
        "content": base64.b64encode(file_bytes).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    resp = requests.put(url, json=payload, headers=headers, timeout=20)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Не удалось загрузить фото в GitHub: {resp.status_code} {resp.text}")

    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"


def make_filename(brand: str, model: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in f"{brand}_{model}")
    return f"{safe}_{int(time.time())}.jpg"
