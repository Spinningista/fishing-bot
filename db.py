"""
База данных для журнала уловов на спиннинг.
SQLite: одна файловая база, без внешних сервисов, не боится бесплатных лимитов.
"""
import sqlite3
import difflib
from datetime import datetime, date
from contextlib import contextmanager

from config import DB_PATH, FUZZY_THRESHOLD, RECENT_LIMIT

SCHEMA = """
CREATE TABLE IF NOT EXISTS waters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS spots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    water_id INTEGER NOT NULL REFERENCES waters(id),
    name TEXT NOT NULL,
    UNIQUE(water_id, name)
);

CREATE TABLE IF NOT EXISTS lures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    category TEXT NOT NULL,
    type TEXT NOT NULL,
    model TEXT NOT NULL,
    photo_url TEXT,
    UNIQUE(brand, model)
);

CREATE TABLE IF NOT EXISTS species (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_date TEXT NOT NULL,          -- ISO YYYY-MM-DD
    water_id INTEGER NOT NULL REFERENCES waters(id),
    spot_id INTEGER REFERENCES spots(id),
    condition TEXT NOT NULL,          -- 'С берега' / 'С лодки' / 'Со льда'
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id),
    lure_id INTEGER NOT NULL REFERENCES lures(id),
    species_id INTEGER NOT NULL REFERENCES species(id),
    qty INTEGER NOT NULL DEFAULT 1,
    weight_g INTEGER
);

CREATE INDEX IF NOT EXISTS idx_catches_trip ON catches(trip_id);
CREATE INDEX IF NOT EXISTS idx_trips_water ON trips(water_id);
CREATE INDEX IF NOT EXISTS idx_spots_water ON spots(water_id);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Общая логика "найти похожее / получить или создать" — используется для
# водоёмов, мест ловли и приманок, чтобы защититься от дублей из-за опечаток.
# ---------------------------------------------------------------------------

def find_similar(name: str, candidates: list[str], threshold: float = FUZZY_THRESHOLD) -> str | None:
    """Возвращает самое похожее имя из candidates, если похожесть >= threshold."""
    if not candidates:
        return None
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=threshold)
    return matches[0] if matches else None


# ---------------------------- Водоёмы ----------------------------

def list_waters(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM waters ORDER BY name").fetchall()


def recent_waters(conn, limit: int = RECENT_LIMIT) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT w.*, MAX(t.created_at) as last_used
        FROM waters w JOIN trips t ON t.water_id = w.id
        GROUP BY w.id ORDER BY last_used DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()


def find_similar_water(conn, name: str) -> str | None:
    names = [r["name"] for r in list_waters(conn)]
    return find_similar(name, names)


def create_water(conn, name: str) -> int:
    cur = conn.execute("INSERT INTO waters(name) VALUES (?)", (name,))
    return cur.lastrowid


def get_water_by_name(conn, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM waters WHERE name = ?", (name,)).fetchone()


# ---------------------------- Места ловли ----------------------------

def list_spots(conn, water_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM spots WHERE water_id = ? ORDER BY name", (water_id,)
    ).fetchall()


def find_similar_spot(conn, water_id: int, name: str) -> str | None:
    names = [r["name"] for r in list_spots(conn, water_id)]
    return find_similar(name, names)


def create_spot(conn, water_id: int, name: str) -> int:
    cur = conn.execute(
        "INSERT INTO spots(water_id, name) VALUES (?, ?)", (water_id, name)
    )
    return cur.lastrowid


def get_spot_by_name(conn, water_id: int, name: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM spots WHERE water_id = ? AND name = ?", (water_id, name)
    ).fetchone()


# ---------------------------- Приманки ----------------------------

def list_lures(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM lures ORDER BY brand, model").fetchall()


def recent_lures(conn, limit: int = RECENT_LIMIT) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT l.*, MAX(t.created_at) as last_used
        FROM lures l JOIN catches c ON c.lure_id = l.id JOIN trips t ON t.id = c.trip_id
        GROUP BY l.id ORDER BY last_used DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()


def search_lures(conn, query: str, limit: int = 10) -> list[sqlite3.Row]:
    q = f"%{query.lower()}%"
    return conn.execute(
        """
        SELECT * FROM lures
        WHERE lower(brand || ' ' || model) LIKE ?
        ORDER BY brand, model LIMIT ?
        """,
        (q, limit),
    ).fetchall()


def find_similar_lure(conn, brand: str, model: str) -> sqlite3.Row | None:
    """Ищет похожую приманку по строке 'бренд модель' среди всех существующих."""
    full = f"{brand} {model}"
    rows = list_lures(conn)
    labels = {f"{r['brand']} {r['model']}": r for r in rows}
    match = find_similar(full, list(labels.keys()))
    return labels.get(match) if match else None


def create_lure(conn, brand: str, category: str, type_: str, model: str, photo_url: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO lures(brand, category, type, model, photo_url) VALUES (?, ?, ?, ?, ?)",
        (brand, category, type_, model, photo_url),
    )
    return cur.lastrowid


def set_lure_photo(conn, lure_id: int, photo_url: str):
    conn.execute("UPDATE lures SET photo_url = ? WHERE id = ?", (photo_url, lure_id))


def get_lure(conn, lure_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lures WHERE id = ?", (lure_id,)).fetchone()


def list_categories(conn) -> list[str]:
    rows = conn.execute("SELECT DISTINCT category FROM lures ORDER BY category").fetchall()
    return [r["category"] for r in rows]


def list_types(conn, category: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT type FROM lures WHERE category = ? ORDER BY type", (category,)
    ).fetchall()
    return [r["type"] for r in rows]


def list_brands(conn) -> list[str]:
    rows = conn.execute("SELECT DISTINCT brand FROM lures ORDER BY brand").fetchall()
    return [r["brand"] for r in rows]


# ---------------------------- Виды рыбы ----------------------------

def list_species(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM species ORDER BY name").fetchall()


def frequent_species(conn, limit: int = RECENT_LIMIT) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT s.*, COUNT(*) as cnt FROM species s
        JOIN catches c ON c.species_id = s.id
        GROUP BY s.id ORDER BY cnt DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()


def find_similar_species(conn, name: str) -> str | None:
    names = [r["name"] for r in list_species(conn)]
    return find_similar(name, names)


def create_species(conn, name: str) -> int:
    cur = conn.execute("INSERT INTO species(name) VALUES (?)", (name,))
    return cur.lastrowid


def get_species_by_name(conn, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM species WHERE name = ?", (name,)).fetchone()


# ---------------------------- Выезды и уловы ----------------------------

def create_trip(conn, trip_date: str, water_id: int, spot_id: int | None, condition: str) -> int:
    cur = conn.execute(
        "INSERT INTO trips(trip_date, water_id, spot_id, condition, created_at) VALUES (?, ?, ?, ?, ?)",
        (trip_date, water_id, spot_id, condition, datetime.utcnow().isoformat()),
    )
    return cur.lastrowid


def add_catch(conn, trip_id: int, lure_id: int, species_id: int, qty: int, weight_g: int | None) -> int:
    cur = conn.execute(
        "INSERT INTO catches(trip_id, lure_id, species_id, qty, weight_g) VALUES (?, ?, ?, ?, ?)",
        (trip_id, lure_id, species_id, qty, weight_g),
    )
    return cur.lastrowid


def trip_summary(conn, trip_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.*, l.brand, l.model, s.name as species_name
        FROM catches c
        JOIN lures l ON l.id = c.lure_id
        JOIN species s ON s.id = c.species_id
        WHERE c.trip_id = ?
        """,
        (trip_id,),
    ).fetchall()


def export_slim_rows(conn) -> list[dict]:
    """
    Плоская выгрузка в компактном формате, который напрямую понимает
    дашборд (dashboard.html): ключи d,w,c,cat,typ,br,mdl,f,q,wt,y,sp,ph.
    """
    rows = conn.execute(
        """
        SELECT
            t.trip_date as trip_date,
            w.name as water,
            t.condition as condition,
            l.category as category,
            l.type as type,
            l.brand as brand,
            l.model as model,
            l.photo_url as photo_url,
            sp.name as fish,
            c.qty as qty,
            c.weight_g as weight_g,
            sport.name as spot
        FROM catches c
        JOIN trips t ON t.id = c.trip_id
        JOIN waters w ON w.id = t.water_id
        LEFT JOIN spots sport ON sport.id = t.spot_id
        JOIN lures l ON l.id = c.lure_id
        JOIN species sp ON sp.id = c.species_id
        ORDER BY t.trip_date
        """
    ).fetchall()

    out = []
    for r in rows:
        y, m, d = r["trip_date"].split("-")
        out.append({
            "d": f"{d}.{m}.{y[2:]}",
            "w": r["water"],
            "c": r["condition"],
            "cat": r["category"],
            "typ": r["type"],
            "br": r["brand"],
            "mdl": r["model"],
            "ph": r["photo_url"] or "",
            "f": r["fish"],
            "q": r["qty"],
            "wt": r["weight_g"],
            "y": y,
            "sp": r["spot"] or "",
        })
    return out


def export_all_rows(conn) -> list[dict]:
    """Плоская выгрузка всех данных — формат максимально близкий к исходной таблице Numbers."""
    rows = conn.execute(
        """
        SELECT
            t.trip_date as "Дата",
            w.name as "Водоём",
            t.condition as "Условия",
            l.category as "Вид",
            l.type as "Тип",
            l.brand as "Бренд",
            l.model as "Серия",
            sp.name as "Рыба",
            c.qty as "Кол-во",
            c.weight_g as "Вес",
            sport.name as "Место ловли"
        FROM catches c
        JOIN trips t ON t.id = c.trip_id
        JOIN waters w ON w.id = t.water_id
        LEFT JOIN spots sport ON sport.id = t.spot_id
        JOIN lures l ON l.id = c.lure_id
        JOIN species sp ON sp.id = c.species_id
        ORDER BY t.trip_date
        """
    ).fetchall()
    return [dict(r) for r in rows]
