"""
DataLuatVN — Vietnamese Legal Documents API
Entry point: slim server.py that imports and assembles all routers.
"""

import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DB_NAME, API_PORT, DESCRIPTION, TAGS_METADATA
from app.database import init_admin_db
from app.routers import general, auth, api_keys, laws, anle, phapdien, admin_pages, dashboard_api, admin_crud


# ╔══════════════════════════════════════════════════════════════╗
# ║                       LIFESPAN                             ║
# ╚══════════════════════════════════════════════════════════════╝

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init admin DB, validate main DB."""
    init_admin_db()
    if os.path.exists(DB_NAME):
        try:
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM documents")
            total = cursor.fetchone()[0]
            conn.close()
            print(f"✅ Legal database loaded: {total:,} documents")
        except sqlite3.OperationalError as e:
            print(f"⚠️  Could not count documents on startup (database might be busy): {e}")
    else:
        print(f"⚠️  Legal database '{DB_NAME}' not found. Run download_all_to_sqlite.py first.")
    print(f"🚀 API server starting on port {API_PORT}")
    yield


# ╔══════════════════════════════════════════════════════════════╗
# ║                     APP SETUP                               ║
# ╚══════════════════════════════════════════════════════════════╝

app = FastAPI(
    title="Vietnamese Legal Documents API",
    description=DESCRIPTION,
    version="2.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Pháp sư Tô — dataluatvn"},
    license_info={"name": "MIT"},
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   INCLUDE ROUTERS                           ║
# ╚══════════════════════════════════════════════════════════════╝

app.include_router(general.router)
app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(laws.router)
app.include_router(anle.router)
app.include_router(phapdien.router)
app.include_router(admin_pages.router)
app.include_router(dashboard_api.router)
app.include_router(admin_crud.router)


# ╔══════════════════════════════════════════════════════════════╗
# ║                       MAIN                                 ║
# ╚══════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=API_PORT, reload=True)
