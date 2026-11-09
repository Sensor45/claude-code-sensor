"""Книжный блог на FastAPI: список книг, страница книги и редактирование."""

import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

import auth
import database

BASE_DIR = Path(__file__).resolve().parent
MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
MAX_LENGTHS = {"title": 200, "author": 200, "genre": 60, "summary": 500, "review": 20000}
WORDS_PER_MINUTE = 180


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="Полка", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def template_context(request: Request) -> dict:
    """Добавляет текущего пользователя (или None) в каждый шаблон: от этого зависит меню в шапке."""
    return {"user": auth.user_from_token(request.cookies.get(auth.SESSION_COOKIE))}


templates = Jinja2Templates(directory=BASE_DIR / "templates", context_processors=[template_context])


def format_date(value: str) -> str:
    date = datetime.fromisoformat(value)
    return f"{date.day} {MONTHS[date.month - 1]} {date.year}"


def paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n+", text) if part.strip()]


def reading_time(text: str) -> int:
    return max(1, round(len(text.split()) / WORDS_PER_MINUTE))


def cover_hue(book_id: int) -> int:
    return (book_id * 67 + 20) % 360


templates.env.filters.update(
    format_date=format_date,
    paragraphs=paragraphs,
    reading_time=reading_time,
    cover_hue=cover_hue,
)


def book_form(
    title: str = Form(""),
    author: str = Form(""),
    year: str = Form(""),
    genre: str = Form(""),
    rating: str = Form("0"),
    summary: str = Form(""),
    review: str = Form(""),
) -> dict:
    return {
        "title": title.strip(),
        "author": author.strip(),
        "year": year.strip(),
        "genre": genre.strip(),
        "rating": rating.strip(),
        "summary": summary.replace("\r\n", "\n").strip(),
        "review": review.replace("\r\n", "\n").strip(),
    }


BookForm = Annotated[dict, Depends(book_form)]


def validate(form: dict) -> tuple[dict, dict]:
    """Возвращает данные для записи в базу и ошибки по полям."""
    errors = {}
    if not form["title"]:
        errors["title"] = "Укажите название книги."
    if not form["author"]:
        errors["author"] = "Укажите автора."
    for field, limit in MAX_LENGTHS.items():
        if len(form[field]) > limit:
            errors[field] = f"Не больше {limit} символов."

    year = None
    if form["year"]:
        if form["year"].isascii() and form["year"].isdigit() and 1 <= int(form["year"]) <= 2100:
            year = int(form["year"])
        else:
            errors["year"] = "Год должен быть числом от 1 до 2100."

    rating = 0
    if form["rating"] in {"0", "1", "2", "3", "4", "5"}:
        rating = int(form["rating"])
    else:
        errors["rating"] = "Оценка должна быть от 0 до 5."

    return {**form, "year": year, "rating": rating}, errors


def get_book_or_404(book_id: int) -> dict:
    book = database.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404)
    return book


def render_form(request: Request, book: dict, errors: dict | None = None):
    return templates.TemplateResponse(
        request,
        "edit.html",
        {"book": book, "errors": errors or {}, "genres": database.list_genres()},
        status_code=422 if errors else 200,
    )


@app.get("/")
def index(request: Request, q: str = "", genre: str = "", deleted: bool = False):
    query = q.strip()
    books = database.list_books(query, genre)
    filtered = bool(query or genre)
    featured = books[0] if books and not filtered else None
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "featured": featured,
            "books": books[1:] if featured else books,
            "count": len(books),
            "genres": database.list_genres(),
            "query": query,
            "genre": genre,
            "filtered": filtered,
            "toast": "Книга удалена" if deleted else None,
        },
    )


@app.get("/bestsellers")
def bestsellers(request: Request):
    return templates.TemplateResponse(request, "bestsellers.html", {"books": database.list_top_books()})


@app.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"stats": database.get_stats()})


@app.get("/books/new")
def new_book(request: Request):
    return render_form(request, {"rating": 0})


@app.post("/books/new")
def create_book(request: Request, form: BookForm):
    book, errors = validate(form)
    if errors:
        return render_form(request, form, errors)
    book_id = database.create_book(book)
    return RedirectResponse(f"/books/{book_id}?saved=1", status_code=303)


@app.get("/books/{book_id}")
def show_book(request: Request, book_id: int, saved: bool = False):
    book = get_book_or_404(book_id)
    return templates.TemplateResponse(
        request,
        "book.html",
        {"book": book, "toast": "Изменения сохранены" if saved else None},
    )


@app.get("/books/{book_id}/edit")
def edit_book(request: Request, book_id: int):
    return render_form(request, get_book_or_404(book_id))


@app.post("/books/{book_id}/edit")
def update_book(request: Request, book_id: int, form: BookForm):
    get_book_or_404(book_id)
    book, errors = validate(form)
    if errors:
        return render_form(request, {**form, "id": book_id}, errors)
    database.update_book(book_id, book)
    return RedirectResponse(f"/books/{book_id}?saved=1", status_code=303)


@app.post("/books/{book_id}/delete")
def delete_book(book_id: int):
    get_book_or_404(book_id)
    database.delete_book(book_id)
    return RedirectResponse("/?deleted=1", status_code=303)


# --- Регистрация, вход и личный кабинет ---


def current_user(request: Request) -> dict:
    """Зависимость для защищённых страниц: без входа отправляет на /login."""
    user = auth.user_from_token(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


CurrentUser = Annotated[dict, Depends(current_user)]


def login_response(user_id: int, url: str) -> RedirectResponse:
    """Редирект с cookie сессии. HttpOnly прячет токен от JavaScript, SameSite защищает от CSRF."""
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.start_session(user_id),
        max_age=auth.SESSION_DAYS * 24 * 3600,  # без max_age cookie исчезла бы при закрытии браузера
        httponly=True,
        samesite="lax",
        # secure=True нужно включить, когда сайт работает по HTTPS
    )
    return response


def render_auth(request: Request, template: str, values: dict, errors: dict | None = None):
    return templates.TemplateResponse(
        request, template, {"values": values, "errors": errors or {}}, status_code=422 if errors else 200
    )


@app.get("/register")
def register_page(request: Request):
    if auth.user_from_token(request.cookies.get(auth.SESSION_COOKIE)):
        return RedirectResponse("/account", status_code=303)
    return render_auth(request, "register.html", {})


@app.post("/register")
def register(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
):
    email = auth.normalize_email(email)
    errors = {}
    if error := auth.email_error(email):
        errors["email"] = error
    if error := auth.password_error(password):
        errors["password"] = error
    elif password != password2:
        errors["password2"] = "Пароли не совпадают."

    user_id = None
    if not errors:
        user_id = database.create_user(email, auth.hash_password(password))
        if user_id is None:
            errors["email"] = "Этот email уже зарегистрирован."
    if errors:
        return render_auth(request, "register.html", {"email": email}, errors)
    return login_response(user_id, "/account?welcome=1")


@app.get("/login")
def login_page(request: Request):
    if auth.user_from_token(request.cookies.get(auth.SESSION_COOKIE)):
        return RedirectResponse("/account", status_code=303)
    return render_auth(request, "login.html", {})


@app.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form("")):
    email = auth.normalize_email(email)
    user = auth.check_credentials(email, password)
    if user is None:
        # Одно и то же сообщение для неверного email и неверного пароля, чтобы не раскрывать, кто зарегистрирован.
        return render_auth(request, "login.html", {"email": email}, {"form": "Неверный email или пароль."})
    return login_response(user["id"], "/account")


@app.post("/logout")
def logout(request: Request):
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


def render_account(request: Request, user: dict, errors: dict | None = None, values: dict | None = None, toast=None):
    return templates.TemplateResponse(
        request,
        "account.html",
        {"account": user, "errors": errors or {}, "values": values or {}, "toast": toast},
        status_code=422 if errors else 200,
    )


@app.get("/account")
def account(request: Request, user: CurrentUser, welcome: bool = False, email_changed: bool = False,
            password_changed: bool = False):
    toast = None
    if welcome:
        toast = "Добро пожаловать! Аккаунт создан"
    elif email_changed:
        toast = "Email изменён"
    elif password_changed:
        toast = "Пароль изменён"
    return render_account(request, user, toast=toast)


@app.post("/account/email")
def change_email(request: Request, user: CurrentUser, email: str = Form(""), password: str = Form("")):
    email = auth.normalize_email(email)
    errors = {}
    if error := auth.email_error(email):
        errors["email"] = error
    if not auth.verify_password(password, user["password_hash"]):
        errors["email_password"] = "Неверный текущий пароль."
    if not errors and not database.update_user_email(user["id"], email):
        errors["email"] = "Этот email уже занят."
    if errors:
        return render_account(request, user, errors, {"email": email})
    return RedirectResponse("/account?email_changed=1", status_code=303)


@app.post("/account/password")
def change_password(
    request: Request,
    user: CurrentUser,
    current_password: str = Form(""),
    new_password: str = Form(""),
    new_password2: str = Form(""),
):
    errors = {}
    if not auth.verify_password(current_password, user["password_hash"]):
        errors["current_password"] = "Неверный текущий пароль."
    if error := auth.password_error(new_password):
        errors["new_password"] = error
    elif new_password != new_password2:
        errors["new_password2"] = "Пароли не совпадают."
    if errors:
        return render_account(request, user, errors)

    database.update_user_password(user["id"], auth.hash_password(new_password))
    # Все остальные устройства выходят из аккаунта, текущее остаётся авторизованным.
    auth.end_other_sessions(user["id"], request.cookies[auth.SESSION_COOKIE])
    return RedirectResponse("/account?password_changed=1", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def invalid_url(request: Request, exc: RequestValidationError):
    # Все поля форм необязательны на уровне FastAPI, так что сюда попадают только адреса вроде /books/abc.
    return templates.TemplateResponse(request, "404.html", status_code=404)
