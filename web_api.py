"""
Маленький веб-сервер (aiohttp), который отдаёт данные для дашборда.

Работает в том же процессе, что и Telegram-бот (см. bot.py). Дашборд
теперь отдаётся с того же домена (GET /), поэтому браузер не считает
запрос к /api/catches "чужим" — это убирает проблемы с CORS/file://,
с которыми сталкивался Safari при открытии дашборда как локального файла.
"""
import logging
import os
from aiohttp import web

import config
import db

logger = logging.getLogger("web_api")

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")


async def handle_catches(request: web.Request) -> web.Response:
    token = request.query.get("token", "")
    if not config.API_TOKEN or token != config.API_TOKEN:
        return web.json_response({"error": "unauthorized"}, status=401)

    with db.get_conn() as conn:
        rows = db.export_slim_rows(conn)

    return web.json_response(
        rows,
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def handle_dashboard(request: web.Request) -> web.Response:
    try:
        with open(DASHBOARD_PATH, encoding="utf-8") as f:
            html = f.read()
        return web.Response(text=html, content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="dashboard.html не найден рядом с ботом", status=404)


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/catches", handle_catches)
    return app


async def run_web_app():
    logger.info(f"Starting web API on 0.0.0.0:{config.PORT} (PORT env resolved)")
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.PORT)
    try:
        await site.start()
        logger.info(f"Web API started successfully on port {config.PORT}")
    except Exception:
        logger.exception("Failed to start web API")
        raise
    # держим корутину живой вечно, иначе asyncio.gather сочтёт её завершённой
    import asyncio
    while True:
        await asyncio.sleep(3600)
