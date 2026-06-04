import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

# Resolve static directory relative to the project root (where server.py lives)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    """Serve the admin portal HTML page."""
    html_path = os.path.join(_PROJECT_ROOT, "static", "admin.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=500, detail="Admin page not found.")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard_page():
    """Serve the dashboard HTML page."""
    html_path = os.path.join(_PROJECT_ROOT, "static", "dashboard.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=500, detail="Dashboard page not found.")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
