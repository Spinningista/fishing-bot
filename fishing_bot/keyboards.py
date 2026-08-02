from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


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
