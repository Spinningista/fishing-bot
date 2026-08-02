import csv
import io
from datetime import date


def _to_numbers_date(iso_date: str) -> str:
    """YYYY-MM-DD -> ДД.ММ.ГГ (формат исходной таблицы Numbers)."""
    y, m, d = iso_date.split("-")
    return f"{d}.{m}.{y[2:]}"


def rows_to_csv_bytes(rows: list[dict]) -> bytes:
    columns = ["Дата", "Водоём", "Условия", "Вид", "Тип", "Бренд", "Серия", "Рыба", "Кол-во", "Вес", "Место ловли"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, delimiter=";")
    writer.writeheader()
    for row in rows:
        out = dict(row)
        out["Дата"] = _to_numbers_date(out["Дата"])
        out["Вес"] = f'{out["Вес"]} гр.' if out.get("Вес") else ""
        writer.writerow(out)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
