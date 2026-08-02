"""
Разовый перенос истории из экспортированного из Numbers CSV в базу бота.

Использование:
    python migrate_from_numbers_csv.py "Спиннинг.csv"

Ожидает файл в том же формате, что даёт Numbers при экспорте дашборда
(секции "Данные: Справочник" и "Данные: Данные" внутри одного CSV).
Скрипт идемпотентен настолько, насколько это позволяет UNIQUE в схеме —
повторный запуск на том же файле не создаст дублей водоёмов/приманок/видов
(но может задвоить выезды и уловы, поэтому запускать один раз на чистую базу).
"""
import sys
import re
import csv as csv_module

import db


def parse_weight(w: str):
    if not w:
        return None
    w = w.replace("\xa0", "").replace(" ", "").replace("гр.", "").replace("г.", "")
    try:
        return int(w)
    except ValueError:
        return None


def parse_lure_catalog(lines: list[str]) -> list[dict]:
    start = None
    for i, line in enumerate(lines):
        if line.startswith("Данные: Справочник"):
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        if line.strip() == "" or ":" in line.split(";")[0]:
            break
        fields = line.rstrip("\r\n").split(";")
        if len(fields) < 4:
            continue
        model, brand, category, type_ = fields[0], fields[1], fields[2], fields[3]
        if not brand or not model:
            continue
        out.append({"brand": brand, "category": category, "type": type_, "model": model})
    return out


def parse_main_data(lines: list[str]) -> list[dict]:
    start = None
    for i, line in enumerate(lines):
        if line.startswith("Данные: Данные"):
            start = i + 2  # пропускаем строку заголовка
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        if line.strip() == "":
            continue
        if ":" in line.split(";")[0] and not line.split(";")[0].strip().isdigit():
            break
        fields = line.rstrip("\r\n").split(";")
        if len(fields) < 13:
            continue
        if fields[0].strip().isdigit() and fields[1].strip() == "":
            continue  # строка-разделитель года
        rec = {
            "date": fields[1], "water": fields[2], "condition": fields[3],
            "category": fields[4], "type": fields[5], "brand": fields[6],
            "model": fields[7], "fish": fields[8], "qty": fields[9],
            "weight": fields[10], "year": fields[11], "spot": fields[12],
        }
        out.append(rec)
    return out


def to_iso_date(d: str, year: str) -> str:
    day, month, _ = d.split(".")
    return f"{year}-{month}-{day}"


def run(path: str):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    catalog = parse_lure_catalog(lines)
    records = parse_main_data(lines)
    print(f"Справочник приманок: {len(catalog)} записей")
    print(f"Записи уловов: {len(records)}")

    db.init_db()
    with db.get_conn() as conn:
        # 1. Справочник приманок
        for item in catalog:
            existing = conn.execute(
                "SELECT id FROM lures WHERE brand=? AND model=?", (item["brand"], item["model"])
            ).fetchone()
            if not existing:
                db.create_lure(conn, item["brand"], item["category"], item["type"], item["model"])

        trip_cache = {}  # (date_iso, water, spot, condition) -> trip_id
        water_cache = {}
        spot_cache = {}
        species_cache = {}
        lure_cache = {}
        skipped = 0

        for rec in records:
            if not rec["date"] or not rec["water"] or not rec["fish"] or not rec["brand"]:
                skipped += 1
                continue

            # водоём
            water_name = rec["water"]
            if water_name not in water_cache:
                w = db.get_water_by_name(conn, water_name)
                water_cache[water_name] = w["id"] if w else db.create_water(conn, water_name)
            water_id = water_cache[water_name]

            # место
            spot_id = None
            if rec["spot"]:
                spot_key = (water_id, rec["spot"])
                if spot_key not in spot_cache:
                    sp = db.get_spot_by_name(conn, water_id, rec["spot"])
                    spot_cache[spot_key] = sp["id"] if sp else db.create_spot(conn, water_id, rec["spot"])
                spot_id = spot_cache[spot_key]

            # выезд (группируем по дате+водоёму+месту+условиям)
            trip_key = (rec["date"], water_id, spot_id, rec["condition"])
            if trip_key not in trip_cache:
                iso_date = to_iso_date(rec["date"], rec["year"])
                trip_cache[trip_key] = db.create_trip(conn, iso_date, water_id, spot_id, rec["condition"])
            trip_id = trip_cache[trip_key]

            # приманка
            lure_key = (rec["brand"], rec["model"])
            if lure_key not in lure_cache:
                l = conn.execute(
                    "SELECT id FROM lures WHERE brand=? AND model=?", lure_key
                ).fetchone()
                if not l:
                    new_id = db.create_lure(conn, rec["brand"], rec["category"], rec["type"], rec["model"])
                    lure_cache[lure_key] = new_id
                else:
                    lure_cache[lure_key] = l["id"]
            lure_id = lure_cache[lure_key]

            # вид рыбы
            fish = rec["fish"]
            if fish not in species_cache:
                s = db.get_species_by_name(conn, fish)
                species_cache[fish] = s["id"] if s else db.create_species(conn, fish)
            species_id = species_cache[fish]

            qty = int(rec["qty"]) if rec["qty"].strip().isdigit() else 1
            weight_g = parse_weight(rec["weight"])

            db.add_catch(conn, trip_id, lure_id, species_id, qty, weight_g)

        print(f"Перенесено уловов: {len(records) - skipped}, пропущено (неполные строки): {skipped}")
        print(f"Создано выездов: {len(trip_cache)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python migrate_from_numbers_csv.py путь_к_файлу.csv")
        sys.exit(1)
    run(sys.argv[1])
