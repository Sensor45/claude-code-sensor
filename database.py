"""Работа с базой SQLite: схема, стартовые записи и запросы к таблице книг."""

import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "books.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    author     TEXT    NOT NULL,
    year       INTEGER,
    genre      TEXT    NOT NULL DEFAULT '',
    rating     INTEGER NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
    summary    TEXT    NOT NULL DEFAULT '',
    review     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- В базе лежит только хеш токена: утечка базы не даёт войти по чужой сессии.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
"""

SEED_BOOKS = [
    {
        "title": "Пикник на обочине",
        "author": "Аркадий и Борис Стругацкие",
        "year": 1972,
        "genre": "Фантастика",
        "rating": 5,
        "summary": "Пришельцы задержались на Земле ненадолго и оставили после себя Зону. "
        "Люди до сих пор разбирают мусор, не понимая, что держат в руках.",
        "review": "Самое сильное здесь то, что контакт с иным разумом показан без всякого пафоса. "
        "Никто не прилетел нас учить или завоёвывать: нас просто не заметили.\n\n"
        "Рэдрик Шухарт ходит в Зону не ради науки, а ради денег и семьи, и от этого книга "
        "становится по-настоящему человеческой. Финальная фраза работает так сильно именно "
        "потому, что до неё мы прошли весь путь вместе с героем.",
    },
    {
        "title": "Сто лет одиночества",
        "author": "Габриэль Гарсиа Маркес",
        "year": 1967,
        "genre": "Роман",
        "rating": 5,
        "summary": "История рода Буэндиа и городка Макондо, где чудеса случаются так же "
        "буднично, как дожди и войны.",
        "review": "В первый раз я завёл на полях схему семьи и не жалею об этом: имена повторяются "
        "намеренно, и в этом весь смысл. Поколения ходят по одному кругу и наступают на те же грабли.\n\n"
        "Маркес пишет о невероятном тоном бабушкиного рассказа, и ты перестаёшь удивляться "
        "летающим простыням, зато сильнее чувствуешь обычное одиночество.",
    },
    {
        "title": "1984",
        "author": "Джордж Оруэлл",
        "year": 1949,
        "genre": "Антиутопия",
        "rating": 4,
        "summary": "Уинстон Смит переписывает прошлое по заказу партии и однажды решается "
        "завести дневник. Этого достаточно, чтобы всё рухнуло.",
        "review": "Книга пугает не слежкой, а тем, как система работает с языком. Если нет слова, "
        "то мысль становится трудно даже додумать.\n\n"
        "Середина с трактатом Голдстейна провисает, но последняя часть написана так, что "
        "откладывать её не хочется, хотя читать тяжело.",
    },
    {
        "title": "Мастер и Маргарита",
        "author": "Михаил Булгаков",
        "year": 1967,
        "genre": "Классика",
        "rating": 5,
        "summary": "Воланд со свитой приезжает в Москву, а в ящике стола лежит роман о Понтии "
        "Пилате. Две истории сходятся в одну.",
        "review": "Московские главы смешные и злые, ершалаимские строгие и холодные, и этот контраст "
        "держит всю книгу.\n\n"
        "Перечитывал несколько раз и каждый раз находил новую главную линию: сначала сатиру, "
        "потом любовь, а теперь историю о трусости и о цене, которую за неё платят.",
    },
    {
        "title": "Дюна",
        "author": "Фрэнк Герберт",
        "year": 1965,
        "genre": "Фантастика",
        "rating": 4,
        "summary": "Пустынная планета, единственный источник пряности и юный наследник, "
        "которого одни считают мессией, а другие разменной фигурой.",
        "review": "Мир продуман на уровне экологии, религии и экономики, и поэтому ему веришь. "
        "Вода здесь важнее золота, и это видно в каждой бытовой детали.\n\n"
        "Герберт не воспевает избранного героя, а предупреждает о нём. Эту мысль легко "
        "упустить за приключениями, но именно она оставляет послевкусие.",
    },
    {
        "title": "Преступление и наказание",
        "author": "Фёдор Достоевский",
        "year": 1866,
        "genre": "Классика",
        "rating": 5,
        "summary": "Бывший студент решает проверить собственную теорию топором. Настоящее "
        "наказание начинается раньше любого суда.",
        "review": "Читается как психологический триллер: убийца известен с первых страниц, а напряжение "
        "только растёт. Разговоры Раскольникова с Порфирием держат не хуже погони.\n\n"
        "Душный летний Петербург здесь отдельный персонаж. После книги ещё долго хочется "
        "открыть окно.",
    },
]

BOOK_FIELDS = ("title", "author", "year", "genre", "rating", "summary", "review")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # без этого ON DELETE CASCADE у сессий не сработает
    # Встроенные LOWER и LIKE в SQLite учитывают регистр кириллицы, поэтому для поиска нужна своя функция.
    conn.create_function("fold", 1, lambda value: value.casefold() if value else "", deterministic=True)
    return conn


def init_db() -> None:
    """Создаёт таблицу и один раз добавляет примеры, чтобы после удаления они не возвращались."""
    with closing(connect()) as conn, conn:
        conn.executescript(SCHEMA)
        conn.executescript(AUTH_SCHEMA)
        if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
            for book in SEED_BOOKS:
                _insert(conn, book)
            conn.execute("PRAGMA user_version = 1")


def _insert(conn: sqlite3.Connection, book: dict) -> int:
    columns = ", ".join(BOOK_FIELDS)
    placeholders = ", ".join(f":{field}" for field in BOOK_FIELDS)
    cursor = conn.execute(f"INSERT INTO books ({columns}) VALUES ({placeholders})", book)
    return cursor.lastrowid


def list_books(query: str = "", genre: str = "") -> list[dict]:
    sql = "SELECT * FROM books"
    conditions, params = [], []
    if query:
        escaped = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("(fold(title) LIKE ? ESCAPE '\\' OR fold(author) LIKE ? ESCAPE '\\')")
        params += [f"%{escaped}%"] * 2
    if genre:
        conditions.append("genre = ?")
        params.append(genre)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC, id DESC"
    with closing(connect()) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def list_top_books(limit: int = 12) -> list[dict]:
    """Книги с наивысшими оценками: данных о продажах нет, поэтому «бестселлеры» блога определяются рейтингом."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM books WHERE rating >= 4 ORDER BY rating DESC, created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]


def list_genres() -> list[str]:
    with closing(connect()) as conn:
        rows = conn.execute("SELECT DISTINCT genre FROM books WHERE genre != '' ORDER BY genre")
        return [row["genre"] for row in rows]


def get_stats() -> dict:
    with closing(connect()) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS books,
                   COUNT(DISTINCT NULLIF(genre, '')) AS genres,
                   AVG(NULLIF(rating, 0)) AS rating
            FROM books
            """
        ).fetchone()
    return dict(row)


def get_book(book_id: int) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return dict(row) if row else None


def create_book(book: dict) -> int:
    with closing(connect()) as conn, conn:
        return _insert(conn, book)


def update_book(book_id: int, book: dict) -> None:
    assignments = ", ".join(f"{field} = :{field}" for field in BOOK_FIELDS)
    with closing(connect()) as conn, conn:
        conn.execute(
            f"UPDATE books SET {assignments}, updated_at = datetime('now') WHERE id = :id",
            {**book, "id": book_id},
        )


def delete_book(book_id: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))


# --- Пользователи и сессии ---


def create_user(email: str, password_hash: str) -> int | None:
    """Возвращает id нового пользователя или None, если такой email уже занят."""
    try:
        with closing(connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, password_hash)
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(email: str) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def update_user_email(user_id: int, email: str) -> bool:
    """False, если email уже принадлежит другому пользователю."""
    try:
        with closing(connect()) as conn, conn:
            conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
        return True
    except sqlite3.IntegrityError:
        return False


def update_user_password(user_id: int, password_hash: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def create_session(token_hash: str, user_id: int, expires_at: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")  # заодно чистим просроченные
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )


def get_user_by_session(token_hash: str) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute(
            """
            SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > datetime('now')
            """,
            (token_hash,),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token_hash: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def delete_other_sessions(user_id: int, keep_token_hash: str) -> None:
    """После смены пароля выходим со всех остальных устройств."""
    with closing(connect()) as conn, conn:
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, keep_token_hash)
        )
