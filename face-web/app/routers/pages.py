"""HTML 页面路由：管理后台需登录，平板识别页公开。"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import check_admin_password, clear_login_cookie, set_login_cookie
from app.config import ROOT_DIR

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"title": "登录", "error": ""})


@router.post("/login", response_model=None)
def login_submit(request: Request, password: str = Form("")):
    ok, message = check_admin_password(password)
    if not ok:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"title": "登录", "error": message},
            status_code=401,
        )
    response = RedirectResponse(url="/admin", status_code=303)
    set_login_cookie(response)
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    clear_login_cookie(response)
    return response


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"title": "人脸识别系统"})


@router.get("/admin", response_class=HTMLResponse)
def admin_people(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin_people.html", {"title": "人员管理"})


@router.get("/admin/people/new", response_class=HTMLResponse)
def admin_person_new(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "admin_person.html", {"title": "新建人员", "person_id": None}
    )


@router.get("/admin/people/{person_id}", response_class=HTMLResponse)
def admin_person_detail(request: Request, person_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "admin_person.html", {"title": "人员详情", "person_id": person_id}
    )


@router.get("/admin/logs", response_class=HTMLResponse)
def admin_logs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin_logs.html", {"title": "识别日志"})


@router.get("/recognize", response_class=HTMLResponse)
def recognize_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "recognize.html", {"title": "人脸识别"})


@router.get("/guide/camera", response_class=HTMLResponse)
def guide_camera(request: Request) -> HTMLResponse:
    """安卓平板可访问的摄像头开通指引（Chrome insecure-origin flag）。"""
    return templates.TemplateResponse(
        request, "guide_camera.html", {"title": "摄像头开通指引"}
    )
