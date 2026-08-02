"""
Маленький веб-сервер (aiohttp), который отдаёт данные для дашборда.

Работает в том же процессе, что и Telegram-бот (см. bot.py). Дашборд
(dashboard.html) обращается к /api/catches и получает свежие данные прямо
из базы — без ручного экспорта.
"""
import json
from aiohttp import web

import config
import db


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


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/api/catches", handle_catches)
    return app


async def run_web_app():
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.PORT)
    await site.start()
