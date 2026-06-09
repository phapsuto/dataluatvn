"""
DataLuatVN — Vietnamese Legal Documents API
Entry point: slim server.py that imports and assembles all routers.
"""

import os
# Configure OpenMP and thread settings before importing any other libraries to prevent macOS crashes
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["DISABLE_LLM_EXPANSION"] = "1"

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DB_NAME, API_PORT, DESCRIPTION, TAGS_METADATA
from app.database import init_admin_db, init_memory_db
from app.routers import general, auth, api_keys, laws, anle, phapdien, admin_pages, dashboard_api, admin_crud, lineage, assistant_memory, chatbot


# ╔══════════════════════════════════════════════════════════════╗
# ║                       LIFESPAN                             ║
# ╚══════════════════════════════════════════════════════════════╝

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init admin DB, validate main DB, init assistant memory DB, init hybrid search."""
    init_admin_db()
    init_memory_db()
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
    
    # Init Hybrid Search (BM25 + FTS5) in background
    import threading
    from app.hybrid_search import init_hybrid_engine
    from app.config import CONTENT_DB
    def _build_hybrid():
        try:
            init_hybrid_engine(DB_NAME, CONTENT_DB)
        except Exception as e:
            print(f"⚠️  Hybrid search init failed: {e}")
    threading.Thread(target=_build_hybrid, daemon=True).start()
    
    # Warm-up: Preload Smart Search model + FAISS index (TÙY CHỌN)
    # Đặt biến PRELOAD_SMART_SEARCH=1 để bật. Mặc định TẮT để tiết kiệm ~1.5 GB RAM.
    if os.environ.get("PRELOAD_SMART_SEARCH", "0") == "1":
        def _warmup_smart_search():
            try:
                from app.routers.laws import get_smart_search_resources
                model, index = get_smart_search_resources()
                if model:
                    print(f"✅ Smart Search model preloaded (device: {model.device})")
                if index:
                    print(f"✅ FAISS index preloaded ({index.ntotal:,} vectors)")
            except Exception as e:
                print(f"⚠️  Smart Search warm-up failed (non-critical): {e}")
        threading.Thread(target=_warmup_smart_search, daemon=True).start()
    else:
        print("ℹ️  Smart Search model sẽ lazy-load khi có truy vấn đầu tiên (tiết kiệm RAM).")
    
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
app.include_router(lineage.router)
app.include_router(assistant_memory.router)
app.include_router(chatbot.router)


# ╔══════════════════════════════════════════════════════════════╗
# ║                       MAIN                                 ║
# ╚══════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=API_PORT, reload=True)
