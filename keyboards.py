from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="🎣 Новый выезд")
    kb.button(text="🗑 Последние уловы")
    kb.button(text="📤 Экспорт в CSV")
    kb.button(text="📷 Добавить фото")
    kb.button(text="🗂 Справочник")
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def _build(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in rows:
        for text, data in row:
            kb.button(text=text, callback_data=data)
    kb.adjust(1)
    return kb.as_markup()


def date_kb() -> InlineKeyboardMarkup:
    return _build([
        [("Сегодня", "date:today")],
        [("Вчера", "date:yesterday")],
        [("Другая дата (ввести)", "date:custom")],
    ])


def choices_kb(items: list[str], prefix: str, extra_new_label: str = "+ Новое") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.button(text=item, callback_data=f"{prefix}:{item}")
    kb.button(text=extra_new_label, callback_data=f"{prefix}:__new__")
    kb.adjust(1)
    return kb.as_markup()


def confirm_kb(yes_data: str, no_data: str, yes_label: str, no_label: str) -> InlineKeyboardMarkup:
    return _build([[(yes_label, yes_data), (no_label, no_data)]])


def condition_kb() -> InlineKeyboardMarkup:
    return _build([
        [("С берега", "cond:С берега")],
        [("С лодки", "cond:С лодки")],
        [("Со льда", "cond:Со льда")],
    ])


def lure_choice_kb(recent: list, prefix: str = "lure") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lure in recent:
        label = f"{lure['brand']} — {lure['model']}"
        kb.button(text=label[:60], callback_data=f"{prefix}:{lure['id']}")
    kb.button(text="🔍 Поиск по справочнику", callback_data=f"{prefix}:__search__")
    kb.button(text="+ Новая приманка", callback_data=f"{prefix}:__new__")
    kb.adjust(1)
    return kb.as_markup()


def lure_search_results_kb(results: list, prefix: str = "lure") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lure in results:
        label = f"{lure['brand']} — {lure['model']}"
        kb.button(text=label[:60], callback_data=f"{prefix}:{lure['id']}")
    kb.button(text="Ничего из этого, добавить новую", callback_data=f"{prefix}:__new__")
    kb.adjust(1)
    return kb.as_markup()


def qty_kb() -> InlineKeyboardMarkup:
    return _build([
        [("1", "qty:1"), ("2", "qty:2"), ("3", "qty:3")],
        [("Другое число", "qty:custom")],
    ])


def weight_kb() -> InlineKeyboardMarkup:
    return _build([
        [("Пропустить", "weight:skip")],
    ])


def after_catch_kb() -> InlineKeyboardMarkup:
    return _build([
        [("➕ Ещё улов в этот же выезд", "after:more")],
        [("✅ Закончить выезд", "after:finish")],
    ])


def skip_photo_kb() -> InlineKeyboardMarkup:
    return _build([
        [("📷 Прикрепить фото", "photo:add")],
        [("Пропустить", "photo:skip")],
    ])


def recent_catches_kb(rows: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in rows:
        label = f"{r['trip_date']} · {r['species_name']} x{r['qty']} · {r['water']}"
        kb.button(text=label[:64], callback_data=f"delcatch:{r['id']}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_kb(catch_id: int) -> InlineKeyboardMarkup:
    return _build([
        [("🗑 Да, удалить", f"delconfirm:{catch_id}:yes"), ("Отмена", f"delconfirm:{catch_id}:no")],
    ])


def catalog_type_kb() -> InlineKeyboardMarkup:
    return _build([
        [("🎣 Приманка", "cattype:lure")],
        [("🌊 Водоём", "cattype:water")],
        [("🐟 Вид рыбы", "cattype:species")],
    ])


def catalog_results_kb(rows: list, prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=r["label"][:60], callback_data=f"{prefix}:{r['id']}")
    kb.adjust(1)
    return kb.as_markup()


def catalog_delete_kb(item_type: str, item_id: int) -> InlineKeyboardMarkup:
    return _build([
        [("🗑 Да, удалить", f"catdel:{item_type}:{item_id}:yes"), ("Отмена", f"catdel:{item_type}:{item_id}:no")],
    ])


def catch_photo_pick_kb(rows: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in rows:
        has_photo = "📷 " if r["photo_url"] else ""
        label = f"{has_photo}{r['trip_date']} · {r['species_name']} x{r['qty']} · {r['water']}"
        kb.button(text=label[:64], callback_data=f"cphpick:{r['id']}")
    kb.adjust(1)
    return kb.as_markup()


def photo_manage_kb(prefix: str, item_id, has_photo: bool) -> InlineKeyboardMarkup:
    rows = [[("📷 Добавить/заменить фото", f"{prefix}:add:{item_id}")]]
    if has_photo:
        rows.append([("🗑 Удалить фото", f"{prefix}:del:{item_id}")])
    rows.append([("Отмена", f"{prefix}:cancel:{item_id}")])
    return _build(rows)


def water_photo_results_kb(rows: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in rows:
        has_photo = "📷 " if r["photo_url"] else ""
        kb.button(text=f"{has_photo}{r['name']}"[:64], callback_data=f"wphpick:{r['id']}")
    kb.adjust(1)
    return kb.as_markup()
