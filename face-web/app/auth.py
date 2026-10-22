"""登录鉴权：HMAC 签名 Cookie，区分 admin / user 角色。"""

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
ROLE_ADMIN = "admin"
ROLE_USER = "user"
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


def make_login_token(role: str) -> str:
    if role not in (ROLE_ADMIN, ROLE_USER):
        raise ValueError(f"invalid role: {role}")
    exp = int(time.time()) + COOKIE_MAX_AGE
    payload = f"2.{role}.{exp}"
    sig = hmac.new(session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_token_role(value: str | None) -> str | None:
    """校验 Cookie，返回角色；无效或过期返回 None。旧版无角色 Cookie 一律失效。"""
    if not value:
        return None
    parts = value.split(".")
    if len(parts) != 4:
        return None
    version, role, exp_s, sig = parts
    if version != "2" or role not in (ROLE_ADMIN, ROLE_USER):
        return None
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    payload = f"2.{role}.{exp_s}"
    expected = hmac.new(session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return role


def check_login_password(password: str) -> tuple[str | None, str]:
    """校验密码，返回 (role, error)。先比管理员，再比普通用户；两者相同则视为管理员。"""
    admin_pwd = os.environ.get("FACE_WEB_ADMIN_PWD", "")
    user_pwd = os.environ.get("FACE_WEB_USER_PWD", "")
    if not admin_pwd and not user_pwd:
        return None, "服务器未设置 FACE_WEB_ADMIN_PWD / FACE_WEB_USER_PWD，无法登录"
    if admin_pwd and secrets.compare_digest(password, admin_pwd):
        return ROLE_ADMIN, ""
    if user_pwd and secrets.compare_digest(password, user_pwd):
        return ROLE_USER, ""
    return None, "密码错误"


def is_public(path: str, method: str) -> bool:
    if path == "/login":
        return True
    if path == "/static" or path.startswith("/static/"):
        return True
    return False


def is_user_allowed(path: str, method: str) -> bool:
    """普通用户可访问的路径（已登录）。"""
    if path == "/":
        return True
    if path == "/recognize" or path.startswith("/recognize/"):
        return True
    if path == "/guide/camera" or path.startswith("/guide/camera/"):
        return True
    if path == "/api/recognize" and method.upper() == "POST":
        return True
    if path == "/logout" and method.upper() == "POST":
        return True
    return False


def set_login_cookie(response: RedirectResponse, role: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_login_token(role),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


def clear_login_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method

    if is_public(path, method):
        return await call_next(request)

    role = parse_token_role(request.cookies.get(COOKIE_NAME))
    if role is None:
        if path.startswith("/api") or path.startswith("/media"):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)

    request.state.role = role

    if role == ROLE_ADMIN:
        return await call_next(request)

    # 普通用户：仅识别相关路径
    if is_user_allowed(path, method):
        return await call_next(request)

    if path.startswith("/api") or path.startswith("/media"):
        return JSONResponse({"detail": "无权限"}, status_code=403)
    return RedirectResponse(url="/recognize", status_code=302)
