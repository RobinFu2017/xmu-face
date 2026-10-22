"""HTML 页面路由：管理后台需 admin；识别页需登录（admin 或 user）。"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    ROLE_ADMIN,
    check_login_password,
    clear_login_cookie,
    login_cooldown_remaining,
    login_trigger_cooldown,
    set_login_cookie,
)
from app.config import ROOT_DIR

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))


def _role(request: Request) -> str | None:
    return getattr(request.state, "role", None)


def _ctx(request: Request, **extra) -> dict:
    return {"role": _role(request), **extra}


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "login.html", _ctx(request, title="登录", error="")
    )


@router.post("/login", response_model=None)
def login_submit(request: Request, password: str = Form("")):
    if login_cooldown_remaining() is not None:
        return templates.TemplateResponse(
            request,
            "login.html",
            _ctx(request, title="登录", error="请稍后再试"),
            status_code=429,
        )

    role, message = check_login_password(password)
    if role is None:
        login_trigger_cooldown()
        return templates.TemplateResponse(
            request,
            "login.html",
            _ctx(request, title="登录", error=message),
            status_code=401,
        )
    dest = "/admin" if role == ROLE_ADMIN else "/recognize"
    response = RedirectResponse(url=dest, status_code=303)
    set_login_cookie(response, role)
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    clear_login_cookie(response)
    return response


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "home.html", _ctx(request, title="人脸识别系统")
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_people(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "admin_people.html", _ctx(request, title="人员管理")
    )


@router.get("/admin/people/new", response_class=HTMLResponse)
def admin_person_new(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "admin_person.html", _ctx(request, title="新建人员", person_id=None)
    )


@router.get("/admin/people/{person_id}", response_class=HTMLResponse)
def admin_person_detail(request: Request, person_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin_person.html",
        _ctx(request, title="人员详情", person_id=person_id),
    )


@router.get("/admin/logs", response_class=HTMLResponse)
def admin_logs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "admin_logs.html", _ctx(request, title="识别日志")
    )


@router.get("/recognize", response_class=HTMLResponse)
def recognize_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "recognize.html", _ctx(request, title="人脸识别")
    )


@router.get("/recognize/stage", response_class=HTMLResponse)
def recognize_stage_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "recognize_stage.html", _ctx(request, title="正式识别")
    )


@router.get("/guide/camera", response_class=HTMLResponse)
def guide_camera(request: Request) -> HTMLResponse:
    """安卓平板可访问的摄像头开通指引（Chrome insecure-origin flag）。"""
    return templates.TemplateResponse(
        request, "guide_camera.html", _ctx(request, title="摄像头开通指引")
    )
