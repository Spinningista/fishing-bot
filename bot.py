"""
Телеграм-бот "Журнал уловов на спиннинг".

Запуск:
    python bot.py

Переменные окружения нужно задать перед запуском (см. .env.example и README.md).
"""
import asyncio
import logging
from datetime import date, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, BufferedInputFile, BotCommand

import config
import db
import keyboards as kb
from states import TripFlow, AddPhotoFlow, CatalogFlow, CatchPhotoFlow, WaterPhotoFlow
import export as export_module
import photo_storage
import web_api

logging.basicConfig(level=logging.INFO)
router = Router()


# ---------------------------------------------------------------------------
# Доступ только для владельца бота
# ---------------------------------------------------------------------------

@router.message.middleware()
async def owner_only_message(handler, event: Message, data):
    if config.OWNER_ID and event.from_user.id != config.OWNER_ID:
        await event.answer("Этот бот приватный и настроен только для одного пользователя.")
        return
    return await handler(event, data)


@router.callback_query.middleware()
async def owner_only_callback(handler, event: CallbackQuery, data):
    if config.OWNER_ID and event.from_user.id != config.OWNER_ID:
        await event.answer("Недоступно", show_alert=True)
        return
    return await handler(event, data)


# ---------------------------------------------------------------------------
# /start и /export
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Журнал уловов на спиннинг 🎣\n\nВыбери действие кнопками внизу экрана, "
        "либо командами:\n\n"
        "/new — начать новый выезд\n"
        "/export — выгрузить весь архив в CSV\n"
        "/addphoto — добавить фото к любой приманке из справочника\n"
        "/recent — последние уловы (можно удалить ошибочную запись)\n"
        "/catalog — удалить приманку, водоём или вид рыбы из справочника\n"
        "/catchphoto — фото конкретного улова (например трофейного)\n"
        "/waterphoto — фото водоёма",
        reply_markup=kb.main_menu_kb(),
    )


@router.message(F.text == "🎣 Новый выезд")
async def menu_new_trip(message: Message, state: FSMContext):
    await cmd_new_trip(message, state)


@router.message(F.text == "🗑 Последние уловы")
async def menu_recent(message: Message):
    await cmd_recent(message)


@router.message(F.text == "📤 Экспорт в CSV")
async def menu_export(message: Message):
    await cmd_export(message)


@router.message(F.text == "📷 Добавить фото")
async def menu_addphoto(message: Message, state: FSMContext):
    await cmd_addphoto(message, state)


@router.message(F.text == "🗂 Справочник")
async def menu_catalog(message: Message, state: FSMContext):
    await cmd_catalog(message, state)



@router.message(Command("export"))
async def cmd_export(message: Message):
    with db.get_conn() as conn:
        rows = db.export_all_rows(conn)
    if not rows:
        await message.answer("Пока нет ни одной записи.")
        return
    csv_bytes = export_module.rows_to_csv_bytes(rows)
    file = BufferedInputFile(csv_bytes, filename="Спиннинг_экспорт.csv")
    await message.answer_document(file, caption=f"Экспорт: {len(rows)} строк улова.")


# ---------------------------------------------------------------------------
# /recent — последние уловы, с возможностью удалить ошибочную запись
# ---------------------------------------------------------------------------

@router.message(Command("recent"))
async def cmd_recent(message: Message):
    with db.get_conn() as conn:
        rows = db.recent_catches(conn, limit=10)
    if not rows:
        await message.answer("Пока нет ни одной записи.")
        return
    await message.answer(
        "Последние уловы — нажми на запись, чтобы удалить её:",
        reply_markup=kb.recent_catches_kb(rows),
    )


@router.callback_query(F.data.startswith("delcatch:"))
async def process_delcatch_choice(callback: CallbackQuery):
    catch_id = int(callback.data.split(":", 1)[1])
    with db.get_conn() as conn:
        row = db.get_catch(conn, catch_id)
    if not row:
        await callback.answer("Запись уже не найдена.", show_alert=True)
        return
    text = (
        f"Удалить эту запись?\n\n"
        f"{row['trip_date']} · {row['water']}\n"
        f"{row['species_name']} x{row['qty']} на {row['brand']} {row['model']}"
        + (f", {row['weight_g']} г" if row['weight_g'] else "")
    )
    await callback.message.answer(text, reply_markup=kb.confirm_delete_kb(catch_id))
    await callback.answer()


@router.callback_query(F.data.startswith("delconfirm:"))
async def process_delconfirm(callback: CallbackQuery):
    _, catch_id, action = callback.data.split(":")
    if action == "yes":
        with db.get_conn() as conn:
            db.delete_catch(conn, int(catch_id))
        await callback.message.answer("Запись удалена ✅")
    else:
        await callback.message.answer("Отменено, запись оставлена.")
    await callback.answer()


# ---------------------------------------------------------------------------
# /addphoto — добавить или заменить фото у любой приманки из справочника
# ---------------------------------------------------------------------------

@router.message(Command("addphoto"))
async def cmd_addphoto(message: Message, state: FSMContext):
    if not config.PHOTOS_ENABLED:
        await message.answer(
            "Хранилище фото ещё не настроено. Нужно задать GITHUB_TOKEN и GITHUB_REPO "
            "в переменных окружения (см. README, шаг про фото приманок)."
        )
        return
    await state.clear()
    await state.set_state(AddPhotoFlow.searching)
    await message.answer("Введи название или бренд приманки, к которой хочешь добавить/заменить фото:")


@router.message(AddPhotoFlow.searching)
async def addphoto_search(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        results = db.search_lures(conn, message.text.strip())
    if not results:
        await message.answer("Ничего не нашёл. Попробуй другой запрос:")
        return
    await message.answer("Нашёл вот что:", reply_markup=kb.lure_search_results_kb(results, prefix="aplure"))


@router.callback_query(AddPhotoFlow.searching, F.data.startswith("aplure:"))
async def addphoto_pick(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "__new__":
        await callback.message.answer("Такой приманки не нашлось. Попробуй другой запрос:")
        await callback.answer()
        return
    lure_id = int(value)
    with db.get_conn() as conn:
        lure = db.get_lure(conn, lure_id)
    await state.update_data(photo_lure_id=lure_id)
    await state.set_state(AddPhotoFlow.waiting_photo)
    await callback.message.answer(f'Пришли фото для "{lure["brand"]} — {lure["model"]}":')
    await callback.answer()


@router.message(AddPhotoFlow.waiting_photo, F.photo)
async def addphoto_receive(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    lure_id = data["photo_lure_id"]
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    with db.get_conn() as conn:
        lure = db.get_lure(conn, lure_id)
        filename = photo_storage.make_filename(lure["brand"], lure["model"])
        try:
            url = photo_storage.upload_photo(file_bytes.read(), filename)
            if url:
                db.set_lure_photo(conn, lure_id, url)
                await message.answer("Фото сохранено ✅ Можешь прислать /addphoto ещё для другой приманки.")
        except Exception as e:
            await message.answer(f"Не получилось загрузить фото ({e}).")
    await state.clear()


# ---------------------------------------------------------------------------
# /catchphoto — фото конкретного улова (например трофейной рыбы)
# ---------------------------------------------------------------------------

@router.message(Command("catchphoto"))
async def cmd_catchphoto(message: Message, state: FSMContext):
    if not config.PHOTOS_ENABLED:
        await message.answer(
            "Хранилище фото ещё не настроено. Нужно задать GITHUB_TOKEN и GITHUB_REPO "
            "в переменных окружения (см. README, шаг про фото приманок)."
        )
        return
    await state.clear()
    with db.get_conn() as conn:
        rows = db.recent_catches(conn, limit=15)
    if not rows:
        await message.answer("Пока нет ни одной записи улова.")
        return
    await state.set_state(CatchPhotoFlow.choosing)
    await message.answer(
        "К какому улову добавить фото? (📷 — уже есть фото)",
        reply_markup=kb.catch_photo_pick_kb(rows),
    )


@router.callback_query(CatchPhotoFlow.choosing, F.data.startswith("cphpick:"))
async def catchphoto_pick(callback: CallbackQuery, state: FSMContext):
    catch_id = int(callback.data.split(":", 1)[1])
    with db.get_conn() as conn:
        c = db.get_catch(conn, catch_id)
    if not c:
        await callback.answer("Эта запись уже не найдена.", show_alert=True)
        return
    text = f"{c['trip_date']} · {c['species_name']} x{c['qty']} на {c['brand']} {c['model']}"
    await callback.message.answer(text, reply_markup=kb.photo_manage_kb("cph", catch_id, bool(c["photo_url"])))
    await callback.answer()


@router.callback_query(F.data.startswith("cph:"))
async def catchphoto_manage(callback: CallbackQuery, state: FSMContext):
    _, action, catch_id = callback.data.split(":")
    catch_id = int(catch_id)
    if action == "add":
        await state.update_data(photo_catch_id=catch_id)
        await state.set_state(CatchPhotoFlow.waiting_photo)
        await callback.message.answer("Пришли фото улова:")
    elif action == "del":
        with db.get_conn() as conn:
            db.set_catch_photo(conn, catch_id, None)
        await callback.message.answer("Фото удалено ✅")
        await state.clear()
    else:
        await callback.message.answer("Отменено.")
        await state.clear()
    await callback.answer()


@router.message(CatchPhotoFlow.waiting_photo, F.photo)
async def catchphoto_receive(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    catch_id = data["photo_catch_id"]
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    with db.get_conn() as conn:
        c = db.get_catch(conn, catch_id)
        filename = photo_storage.make_filename("catch", str(catch_id), c["species_name"])
        try:
            url = photo_storage.upload_photo(file_bytes.read(), filename, folder="catch_photos")
            if url:
                db.set_catch_photo(conn, catch_id, url)
                await message.answer("Фото сохранено ✅ Можешь прислать /catchphoto ещё для другого улова.")
        except Exception as e:
            await message.answer(f"Не получилось загрузить фото ({e}).")
    await state.clear()


# ---------------------------------------------------------------------------
# /waterphoto — фото водоёма
# ---------------------------------------------------------------------------

@router.message(Command("waterphoto"))
async def cmd_waterphoto(message: Message, state: FSMContext):
    if not config.PHOTOS_ENABLED:
        await message.answer(
            "Хранилище фото ещё не настроено. Нужно задать GITHUB_TOKEN и GITHUB_REPO "
            "в переменных окружения (см. README, шаг про фото приманок)."
        )
        return
    await state.clear()
    await state.set_state(WaterPhotoFlow.searching)
    await message.answer("Введи название водоёма для поиска:")


@router.message(WaterPhotoFlow.searching)
async def waterphoto_search(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        rows = db.search_waters(conn, message.text.strip())
    if not rows:
        await message.answer("Ничего не нашёл. Попробуй другой запрос:")
        return
    await message.answer("Нашёл вот что:", reply_markup=kb.water_photo_results_kb(rows))


@router.callback_query(WaterPhotoFlow.searching, F.data.startswith("wphpick:"))
async def waterphoto_pick(callback: CallbackQuery, state: FSMContext):
    water_id = int(callback.data.split(":", 1)[1])
    with db.get_conn() as conn:
        w = db.get_water(conn, water_id)
    if not w:
        await callback.answer("Этот водоём уже не найден.", show_alert=True)
        return
    await callback.message.answer(
        f'Водоём: "{w["name"]}"',
        reply_markup=kb.photo_manage_kb("wph", water_id, bool(w["photo_url"])),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wph:"))
async def waterphoto_manage(callback: CallbackQuery, state: FSMContext):
    _, action, water_id = callback.data.split(":")
    water_id = int(water_id)
    if action == "add":
        await state.update_data(photo_water_id=water_id)
        await state.set_state(WaterPhotoFlow.waiting_photo)
        await callback.message.answer("Пришли фото водоёма:")
    elif action == "del":
        with db.get_conn() as conn:
            db.set_water_photo(conn, water_id, None)
        await callback.message.answer("Фото удалено ✅")
        await state.clear()
    else:
        await callback.message.answer("Отменено.")
        await state.clear()
    await callback.answer()


@router.message(WaterPhotoFlow.waiting_photo, F.photo)
async def waterphoto_receive(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    water_id = data["photo_water_id"]
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    with db.get_conn() as conn:
        w = db.get_water(conn, water_id)
        filename = photo_storage.make_filename("water", w["name"])
        try:
            url = photo_storage.upload_photo(file_bytes.read(), filename, folder="water_photos")
            if url:
                db.set_water_photo(conn, water_id, url)
                await message.answer("Фото сохранено ✅ Можешь прислать /waterphoto ещё для другого водоёма.")
        except Exception as e:
            await message.answer(f"Не получилось загрузить фото ({e}).")
    await state.clear()


# ---------------------------------------------------------------------------
# /catalog — удаление приманок, водоёмов и видов рыбы из справочника
# ---------------------------------------------------------------------------

CATALOG_LABELS = {"lure": "приманку", "water": "водоём", "species": "вид рыбы"}
CATALOG_SEARCH_PROMPT = {
    "lure": "Введи название или бренд приманки для поиска:",
    "water": "Введи название водоёма для поиска:",
    "species": "Введи название вида рыбы для поиска:",
}


@router.message(Command("catalog"))
async def cmd_catalog(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CatalogFlow.choosing_type)
    await message.answer(
        "Что хочешь удалить из справочника?",
        reply_markup=kb.catalog_type_kb(),
    )


@router.callback_query(CatalogFlow.choosing_type, F.data.startswith("cattype:"))
async def catalog_choose_type(callback: CallbackQuery, state: FSMContext):
    item_type = callback.data.split(":", 1)[1]
    await state.update_data(catalog_type=item_type)
    await state.set_state(CatalogFlow.searching)
    await callback.message.answer(CATALOG_SEARCH_PROMPT[item_type])
    await callback.answer()


@router.message(CatalogFlow.searching)
async def catalog_search(message: Message, state: FSMContext):
    data = await state.get_data()
    item_type = data["catalog_type"]
    query = message.text.strip()

    with db.get_conn() as conn:
        if item_type == "lure":
            rows = db.search_lures(conn, query)
            items = [{"id": r["id"], "label": f"{r['brand']} — {r['model']}"} for r in rows]
        elif item_type == "water":
            rows = db.search_waters(conn, query)
            items = [{"id": r["id"], "label": r["name"]} for r in rows]
        else:
            rows = db.search_species(conn, query)
            items = [{"id": r["id"], "label": r["name"]} for r in rows]

    if not items:
        await message.answer("Ничего не нашёл. Попробуй другой запрос:")
        return
    await message.answer(
        "Нашёл вот что — выбери, что удалить:",
        reply_markup=kb.catalog_results_kb(items, prefix=f"catpick:{item_type}"),
    )


@router.callback_query(CatalogFlow.searching, F.data.startswith("catpick:"))
async def catalog_pick(callback: CallbackQuery, state: FSMContext):
    _, item_type, item_id = callback.data.split(":")
    item_id = int(item_id)

    with db.get_conn() as conn:
        if item_type == "lure":
            row = db.get_lure(conn, item_id)
            label = f"{row['brand']} — {row['model']}" if row else "?"
            ref_count = db.lure_ref_count(conn, item_id)
        elif item_type == "water":
            row = conn.execute("SELECT * FROM waters WHERE id=?", (item_id,)).fetchone()
            label = row["name"] if row else "?"
            ref_count = db.water_ref_count(conn, item_id)
        else:
            row = conn.execute("SELECT * FROM species WHERE id=?", (item_id,)).fetchone()
            label = row["name"] if row else "?"
            ref_count = db.species_ref_count(conn, item_id)

    if not row:
        await callback.answer("Эта запись уже не найдена.", show_alert=True)
        return

    if ref_count > 0:
        noun = "выездах" if item_type == "water" else "уловах"
        await callback.message.answer(
            f'"{label}" нельзя удалить — используется в {ref_count} {noun}.\n'
            f"Сначала удали эти записи через /recent, потом попробуй снова."
        )
    else:
        await callback.message.answer(
            f'Удалить {CATALOG_LABELS[item_type]} "{label}" из справочника?',
            reply_markup=kb.catalog_delete_kb(item_type, item_id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("catdel:"))
async def catalog_delete_confirm(callback: CallbackQuery, state: FSMContext):
    _, item_type, item_id, action = callback.data.split(":")
    item_id = int(item_id)

    if action == "yes":
        with db.get_conn() as conn:
            if item_type == "lure":
                if db.lure_ref_count(conn, item_id) == 0:
                    db.delete_lure(conn, item_id)
                else:
                    await callback.message.answer("Уже используется в уловах, удаление отменено.")
                    await callback.answer()
                    return
            elif item_type == "water":
                if db.water_ref_count(conn, item_id) == 0:
                    db.delete_water(conn, item_id)
                else:
                    await callback.message.answer("Уже используется в выездах, удаление отменено.")
                    await callback.answer()
                    return
            else:
                if db.species_ref_count(conn, item_id) == 0:
                    db.delete_species(conn, item_id)
                else:
                    await callback.message.answer("Уже используется в уловах, удаление отменено.")
                    await callback.answer()
                    return
        await callback.message.answer("Удалено ✅")
    else:
        await callback.message.answer("Отменено.")
    await state.clear()
    await callback.answer()


@router.message(Command("new"))
async def cmd_new_trip(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(TripFlow.choosing_date)
    await message.answer("Когда рыбачили?", reply_markup=kb.date_kb())


@router.callback_query(TripFlow.choosing_date, F.data.startswith("date:"))
async def process_date_choice(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    if action == "today":
        await set_trip_date(callback.message, state, date.today())
    elif action == "yesterday":
        await set_trip_date(callback.message, state, date.today() - timedelta(days=1))
    else:
        await state.set_state(TripFlow.entering_date)
        await callback.message.answer("Введи дату в формате ДД.ММ.ГГГГ (например 15.07.2026):")
    await callback.answer()


@router.message(TripFlow.entering_date)
async def process_custom_date(message: Message, state: FSMContext):
    try:
        day, month, year = message.text.strip().split(".")
        d = date(int(year), int(month), int(day))
    except Exception:
        await message.answer("Не понял дату. Формат: ДД.ММ.ГГГГ, например 15.07.2026")
        return
    await set_trip_date(message, state, d)


async def set_trip_date(message: Message, state: FSMContext, d: date):
    await state.update_data(trip_date=d.isoformat())
    await ask_water(message, state)


async def ask_water(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        recent = db.recent_waters(conn)
    names = [r["name"] for r in recent]
    await state.set_state(TripFlow.choosing_water)
    await message.answer("Водоём?", reply_markup=kb.choices_kb(names, "water", "+ Новый водоём"))


@router.callback_query(TripFlow.choosing_water, F.data.startswith("water:"))
async def process_water_choice(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "__new__":
        await state.set_state(TripFlow.entering_new_water)
        await callback.message.answer("Название нового водоёма:")
    else:
        with db.get_conn() as conn:
            water = db.get_water_by_name(conn, value)
        await state.update_data(water_id=water["id"], water_name=water["name"])
        await ask_spot(callback.message, state)
    await callback.answer()


@router.message(TripFlow.entering_new_water)
async def process_new_water_name(message: Message, state: FSMContext):
    name = message.text.strip()
    with db.get_conn() as conn:
        similar = db.find_similar_water(conn, name)
    if similar and similar.lower() != name.lower():
        await state.update_data(pending_new_water=name, pending_similar_water=similar)
        await state.set_state(TripFlow.confirming_water_match)
        await message.answer(
            f'Похоже на уже существующий водоём "{similar}". Это он?',
            reply_markup=kb.confirm_kb("waterconfirm:yes", "waterconfirm:no", f"Да, это {similar}", "Нет, другой"),
        )
    else:
        await create_and_use_water(message, state, name)


@router.callback_query(TripFlow.confirming_water_match, F.data.startswith("waterconfirm:"))
async def process_water_confirm(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if action == "yes":
        with db.get_conn() as conn:
            water = db.get_water_by_name(conn, data["pending_similar_water"])
        await state.update_data(water_id=water["id"], water_name=water["name"])
        await ask_spot(callback.message, state)
    else:
        await create_and_use_water(callback.message, state, data["pending_new_water"])
    await callback.answer()


async def create_and_use_water(message: Message, state: FSMContext, name: str):
    with db.get_conn() as conn:
        water_id = db.create_water(conn, name)
    await state.update_data(water_id=water_id, water_name=name)
    await message.answer(f'Добавил новый водоём: "{name}"')
    await ask_spot(message, state)


# ---------------------------------------------------------------------------
# Место ловли (привязано к водоёму)
# ---------------------------------------------------------------------------

async def ask_spot(message: Message, state: FSMContext):
    data = await state.get_data()
    with db.get_conn() as conn:
        spots = db.list_spots(conn, data["water_id"])
    names = [r["name"] for r in spots]
    await state.set_state(TripFlow.choosing_spot)
    if names:
        await message.answer("Место ловли?", reply_markup=kb.choices_kb(names, "spot", "+ Новое место"))
    else:
        await message.answer(
            "Место ловли? (для этого водоёма ещё нет сохранённых мест)",
            reply_markup=kb.choices_kb([], "spot", "+ Новое место"),
        )


@router.callback_query(TripFlow.choosing_spot, F.data.startswith("spot:"))
async def process_spot_choice(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "__new__":
        await state.set_state(TripFlow.entering_new_spot)
        await callback.message.answer("Название нового места ловли:")
    else:
        data = await state.get_data()
        with db.get_conn() as conn:
            spot = db.get_spot_by_name(conn, data["water_id"], value)
        await state.update_data(spot_id=spot["id"])
        await ask_condition(callback.message, state)
    await callback.answer()


@router.message(TripFlow.entering_new_spot)
async def process_new_spot_name(message: Message, state: FSMContext):
    name = message.text.strip()
    data = await state.get_data()
    with db.get_conn() as conn:
        similar = db.find_similar_spot(conn, data["water_id"], name)
    if similar and similar.lower() != name.lower():
        await state.update_data(pending_new_spot=name, pending_similar_spot=similar)
        await state.set_state(TripFlow.confirming_spot_match)
        await message.answer(
            f'Похоже на уже существующее место "{similar}". Это оно?',
            reply_markup=kb.confirm_kb("spotconfirm:yes", "spotconfirm:no", f"Да, это {similar}", "Нет, другое"),
        )
    else:
        await create_and_use_spot(message, state, name)


@router.callback_query(TripFlow.confirming_spot_match, F.data.startswith("spotconfirm:"))
async def process_spot_confirm(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if action == "yes":
        with db.get_conn() as conn:
            spot = db.get_spot_by_name(conn, data["water_id"], data["pending_similar_spot"])
        await state.update_data(spot_id=spot["id"])
        await ask_condition(callback.message, state)
    else:
        await create_and_use_spot(callback.message, state, data["pending_new_spot"])
    await callback.answer()


async def create_and_use_spot(message: Message, state: FSMContext, name: str):
    data = await state.get_data()
    with db.get_conn() as conn:
        spot_id = db.create_spot(conn, data["water_id"], name)
    await state.update_data(spot_id=spot_id)
    await message.answer(f'Добавил новое место: "{name}"')
    await ask_condition(message, state)


# ---------------------------------------------------------------------------
# Условия ловли
# ---------------------------------------------------------------------------

async def ask_condition(message: Message, state: FSMContext):
    await state.set_state(TripFlow.choosing_condition)
    await message.answer("Как ловили?", reply_markup=kb.condition_kb())


@router.callback_query(TripFlow.choosing_condition, F.data.startswith("cond:"))
async def process_condition(callback: CallbackQuery, state: FSMContext):
    condition = callback.data.split(":", 1)[1]
    data = await state.get_data()
    with db.get_conn() as conn:
        trip_id = db.create_trip(conn, data["trip_date"], data["water_id"], data.get("spot_id"), condition)
    await state.update_data(trip_id=trip_id, condition=condition)
    await callback.message.answer(f'Выезд начат: {data["trip_date"]}, {data["water_name"]}, {condition}.')
    await ask_lure(callback.message, state)
    await callback.answer()


# ---------------------------------------------------------------------------
# Цикл добавления улова: приманка -> рыба -> кол-во -> вес -> ещё/закончить
# ---------------------------------------------------------------------------

async def ask_lure(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        recent = db.recent_lures(conn)
    await state.set_state(TripFlow.choosing_lure)
    await message.answer("Какая приманка?", reply_markup=kb.lure_choice_kb(recent))


@router.callback_query(TripFlow.choosing_lure, F.data.startswith("lure:"))
async def process_lure_choice(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "__search__":
        await state.set_state(TripFlow.searching_lure)
        await callback.message.answer("Введи часть названия приманки или бренда для поиска:")
    elif value == "__new__":
        await state.set_state(TripFlow.entering_new_lure_brand)
        await callback.message.answer("Бренд новой приманки:")
    else:
        await use_lure(callback.message, state, int(value))
    await callback.answer()


@router.message(TripFlow.searching_lure)
async def process_lure_search(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        results = db.search_lures(conn, message.text.strip())
    if not results:
        await message.answer(
            "Ничего не нашёл по этому запросу.",
            reply_markup=kb.lure_search_results_kb([]),
        )
        return
    await message.answer("Нашёл вот что:", reply_markup=kb.lure_search_results_kb(results))


@router.callback_query(TripFlow.searching_lure, F.data.startswith("lure:"))
async def process_lure_search_choice(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "__new__":
        await state.set_state(TripFlow.entering_new_lure_brand)
        await callback.message.answer("Бренд новой приманки:")
    else:
        await use_lure(callback.message, state, int(value))
    await callback.answer()


@router.message(TripFlow.entering_new_lure_brand)
async def process_new_lure_brand(message: Message, state: FSMContext):
    await state.update_data(new_lure_brand=message.text.strip())
    await state.set_state(TripFlow.entering_new_lure_category)
    await message.answer("Категория приманки (например: Воблеры, Силиконовые приманки, Блёсны):")


@router.message(TripFlow.entering_new_lure_category)
async def process_new_lure_category(message: Message, state: FSMContext):
    await state.update_data(new_lure_category=message.text.strip())
    await state.set_state(TripFlow.entering_new_lure_type)
    await message.answer("Тип/подтип приманки (например: Виброхвосты, Вращающиеся блёсны):")


@router.message(TripFlow.entering_new_lure_type)
async def process_new_lure_type(message: Message, state: FSMContext):
    await state.update_data(new_lure_type=message.text.strip())
    await state.set_state(TripFlow.entering_new_lure_model)
    await message.answer("Конкретная модель/серия (например: Tioga 2.4 #F08):")


@router.message(TripFlow.entering_new_lure_model)
async def process_new_lure_model(message: Message, state: FSMContext):
    model = message.text.strip()
    data = await state.get_data()
    brand = data["new_lure_brand"]
    with db.get_conn() as conn:
        similar = db.find_similar_lure(conn, brand, model)
    if similar:
        label = f"{similar['brand']} — {similar['model']}"
        await state.update_data(pending_new_lure_model=model, pending_similar_lure_id=similar["id"])
        await state.set_state(TripFlow.confirming_lure_match)
        await message.answer(
            f'Похоже на уже существующую приманку "{label}". Это она?',
            reply_markup=kb.confirm_kb("lureconfirm:yes", "lureconfirm:no", f"Да, это она", "Нет, другая"),
        )
    else:
        await create_and_use_lure(message, state, brand, data["new_lure_category"], data["new_lure_type"], model)


@router.callback_query(TripFlow.confirming_lure_match, F.data.startswith("lureconfirm:"))
async def process_lure_confirm(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if action == "yes":
        await use_lure(callback.message, state, data["pending_similar_lure_id"])
    else:
        await create_and_use_lure(
            callback.message, state,
            data["new_lure_brand"], data["new_lure_category"], data["new_lure_type"], data["pending_new_lure_model"],
        )
    await callback.answer()


async def create_and_use_lure(message: Message, state: FSMContext, brand, category, type_, model):
    with db.get_conn() as conn:
        lure_id = db.create_lure(conn, brand, category, type_, model)
    await state.update_data(current_lure_id=lure_id)
    await message.answer(f'Добавил новую приманку: "{brand} — {model}"')
    if config.PHOTOS_ENABLED:
        await state.set_state(TripFlow.asking_lure_photo)
        await message.answer("Хочешь прикрепить фото этой приманки?", reply_markup=kb.skip_photo_kb())
    else:
        await use_lure(message, state, lure_id, skip_message=True)


@router.callback_query(TripFlow.asking_lure_photo, F.data.startswith("photo:"))
async def process_photo_choice(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    if action == "add":
        await state.set_state(TripFlow.waiting_lure_photo)
        await callback.message.answer("Пришли фото приманки:")
    else:
        data = await state.get_data()
        await use_lure(callback.message, state, data["current_lure_id"], skip_message=True)
    await callback.answer()


@router.message(TripFlow.waiting_lure_photo, F.photo)
async def process_lure_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    lure_id = data["current_lure_id"]
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    with db.get_conn() as conn:
        lure = db.get_lure(conn, lure_id)
        filename = photo_storage.make_filename(lure["brand"], lure["model"])
        try:
            url = photo_storage.upload_photo(file_bytes.read(), filename)
            if url:
                db.set_lure_photo(conn, lure_id, url)
                await message.answer("Фото сохранено ✅")
        except Exception as e:
            await message.answer(f"Не получилось загрузить фото ({e}), но улов всё равно сохраню.")

    await use_lure(message, state, lure_id, skip_message=True)


async def use_lure(message: Message, state: FSMContext, lure_id: int, skip_message: bool = False):
    await state.update_data(current_lure_id=lure_id)
    await ask_species(message, state)


# ---------------------------------------------------------------------------
# Вид рыбы
# ---------------------------------------------------------------------------

async def ask_species(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        frequent = db.frequent_species(conn)
    names = [r["name"] for r in frequent]
    await state.set_state(TripFlow.choosing_species)
    await message.answer("Какая рыба?", reply_markup=kb.choices_kb(names, "species", "+ Другой вид"))


@router.callback_query(TripFlow.choosing_species, F.data.startswith("species:"))
async def process_species_choice(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "__new__":
        await state.set_state(TripFlow.entering_new_species)
        await callback.message.answer("Название вида рыбы:")
    else:
        with db.get_conn() as conn:
            species = db.get_species_by_name(conn, value)
        await state.update_data(current_species_id=species["id"])
        await ask_qty(callback.message, state)
    await callback.answer()


@router.message(TripFlow.entering_new_species)
async def process_new_species(message: Message, state: FSMContext):
    name = message.text.strip()
    with db.get_conn() as conn:
        similar = db.find_similar_species(conn, name)
    if similar and similar.lower() != name.lower():
        await state.update_data(pending_new_species=name, pending_similar_species=similar)
        await state.set_state(TripFlow.confirming_species_match)
        await message.answer(
            f'Похоже на уже существующий вид "{similar}". Это он?',
            reply_markup=kb.confirm_kb("speciesconfirm:yes", "speciesconfirm:no", f"Да, это {similar}", "Нет, другой"),
        )
    else:
        await create_and_use_species(message, state, name)


@router.callback_query(TripFlow.confirming_species_match, F.data.startswith("speciesconfirm:"))
async def process_species_confirm(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if action == "yes":
        with db.get_conn() as conn:
            species = db.get_species_by_name(conn, data["pending_similar_species"])
        await state.update_data(current_species_id=species["id"])
        await ask_qty(callback.message, state)
    else:
        await create_and_use_species(callback.message, state, data["pending_new_species"])
    await callback.answer()


async def create_and_use_species(message: Message, state: FSMContext, name: str):
    with db.get_conn() as conn:
        species_id = db.create_species(conn, name)
    await state.update_data(current_species_id=species_id)
    await message.answer(f'Добавил новый вид: "{name}"')
    await ask_qty(message, state)


# ---------------------------------------------------------------------------
# Количество и вес
# ---------------------------------------------------------------------------

async def ask_qty(message: Message, state: FSMContext):
    await state.set_state(TripFlow.entering_qty)
    await message.answer("Сколько поймал этим способом?", reply_markup=kb.qty_kb())


@router.callback_query(TripFlow.entering_qty, F.data.startswith("qty:"))
async def process_qty_choice(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await callback.message.answer("Введи число:")
        await callback.answer()
        return
    await state.update_data(current_qty=int(value))
    await ask_weight(callback.message, state)
    await callback.answer()


@router.message(TripFlow.entering_qty)
async def process_qty_custom(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно просто число, например 2. Попробуй ещё раз:")
        return
    await state.update_data(current_qty=qty)
    await ask_weight(message, state)


async def ask_weight(message: Message, state: FSMContext):
    await state.set_state(TripFlow.entering_weight)
    await message.answer("Вес (в граммах)? Можно пропустить.", reply_markup=kb.weight_kb())


@router.callback_query(TripFlow.entering_weight, F.data == "weight:skip")
async def process_weight_skip(callback: CallbackQuery, state: FSMContext):
    await save_catch_and_continue(callback.message, state, weight_g=None)
    await callback.answer()


@router.message(TripFlow.entering_weight)
async def process_weight_value(message: Message, state: FSMContext):
    try:
        weight = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно число в граммах, например 850. Или нажми «Пропустить» выше.")
        return
    await save_catch_and_continue(message, state, weight_g=weight)


async def save_catch_and_continue(message: Message, state: FSMContext, weight_g):
    data = await state.get_data()
    with db.get_conn() as conn:
        db.add_catch(
            conn,
            trip_id=data["trip_id"],
            lure_id=data["current_lure_id"],
            species_id=data["current_species_id"],
            qty=data["current_qty"],
            weight_g=weight_g,
        )
    await state.set_state(TripFlow.after_catch)
    await message.answer("Записал ✅", reply_markup=kb.after_catch_kb())


@router.callback_query(TripFlow.after_catch, F.data == "after:more")
async def process_more_catch(callback: CallbackQuery, state: FSMContext):
    await ask_lure(callback.message, state)
    await callback.answer()


@router.callback_query(TripFlow.after_catch, F.data == "after:finish")
async def process_finish_trip(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    with db.get_conn() as conn:
        summary = db.trip_summary(conn, data["trip_id"])
    total = sum(r["qty"] for r in summary)
    lines = [f"• {r['species_name']} x{r['qty']} на {r['brand']} {r['model']}" for r in summary]
    text = "Выезд завершён 🎣\nИтого поймано: " + str(total) + "\n\n" + "\n".join(lines)
    await callback.message.answer(text)
    await state.clear()
    await callback.answer()


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

async def main():
    db.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    await bot.set_my_commands([
        BotCommand(command="new", description="🎣 Начать новый выезд"),
        BotCommand(command="recent", description="🗑 Последние уловы (удалить запись)"),
        BotCommand(command="export", description="📤 Выгрузить архив в CSV"),
        BotCommand(command="addphoto", description="📷 Добавить фото приманки"),
        BotCommand(command="catalog", description="🗂 Удалить приманку/водоём/вид рыбы"),
        BotCommand(command="catchphoto", description="🐟 Фото конкретного улова"),
        BotCommand(command="waterphoto", description="🌊 Фото водоёма"),
    ])
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await asyncio.gather(
        dp.start_polling(bot),
        web_api.run_web_app(),
    )


if __name__ == "__main__":
    asyncio.run(main())
