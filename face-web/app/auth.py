"""管理端登录：HMAC 签名 Cookie。识别页与识别接口不校验。"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import DATA_DIR

COOKIE_NAME = "face_admin"
COOKIE_MAX_AGE = 7 * 24 * 3600
_SECRET_FILE = DATA_DIR / "session_secret"


def session_secret() -> bytes:
    """优先环境变量 SESSION_SECRET，否则读写 data/session_secret。"""
    env = os.environ.get("SESSION_SECRET", "").strip()
    if env:
        return env.encode()
    if _SECRET_FILE.exists():
        saved = _SECRET_FILE.read_text(encoding="utf-8").strip()
        if saved:
            return saved.encode()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    _SECRET_FILE.write_text(token, encoding="utf-8")
    return token.encode()


def make_login_token() -> str:
    exp = int(time.time()) + COOKIE_MAX_AGE
    payload = f"1.{exp}"
    sig = hmac.new(session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def token_ok(value: str | None) -> bool:
    if not value:
        return False
    parts = value.split(".")
    if len(parts) != 3:
        return False
    version, exp_s, sig = parts
    if version != "1":
        return False
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"1.{exp_s}"
    expected = hmac.new(session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def check_admin_password(password: str) -> tuple[bool, str]:
    expected = os.environ.get("FACE_WEB_ADMIN_PWD", "")
    if not expected:
        return False, "服务器未设置 FACE_WEB_ADMIN_PWD，无法登录"
    if secrets.compare_digest(password, expected):
        return True, ""
    return False, "密码错误"


def is_public(path: str, method: str) -> bool:
    if path == "/login":
        return True
    if path == "/recognize" or path.startswith("/recognize/"):
        return True
    if path == "/guide/camera" or path.startswith("/guide/camera/"):
        return True
    if path == "/api/recognize" and method.upper() == "POST":
        return True
    if path == "/static" or path.startswith("/static/"):
        return True
    return False


def set_login_cookie(response: RedirectResponse) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_login_token(),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


def clear_login_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


async def auth_middleware(request: Request, call_next):
    if is_public(request.url.path, request.method) or token_ok(request.cookies.get(COOKIE_NAME)):
        return await call_next(request)
    path = request.url.path
    if path.startswith("/api") or path.startswith("/media"):
        return JSONResponse({"detail": "未登录"}, status_code=401)
    return RedirectResponse(url="/login", status_code=302)
