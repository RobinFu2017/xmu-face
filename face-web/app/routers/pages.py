"""HTML 页面路由：管理后台与平板识别页。无登录，知道路径即可打开。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import ROOT_DIR

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))


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
