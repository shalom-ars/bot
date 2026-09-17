from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import threading
import logging
from app.api.endpoints import router as api_router
from app.api.websockets import router as ws_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.admin import router as admin_router
from app.db.session import engine, Base, ensure_btc5m_schema

Base.metadata.create_all(bind=engine)
ensure_btc5m_schema(engine)

from app.api.health import router as health_router
from app.api.markets import router as markets_router
from app.api.signals import router as signals_router
from app.api.btc5m import router as btc5m_router
from app.api.system import router as system_router
from app.engine.scanner import orchestrator
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    Base.metadata.create_all(bind=engine)
    ensure_btc5m_schema(engine)
    logger.info("FastAPI lifecycle start. DB created and BTC5M thesis schema verified.")
    
    from app.config import settings
    if settings.live_trading_enabled or settings.execution_mode == "live":
        raise RuntimeError("REAL TRADING IS DISABLED IN THIS BUILD. Phase 7 hard-block active.")

    from app.research.resolution_checker import resolution_check_loop
    asyncio.create_task(orchestrator.start())
    asyncio.create_task(resolution_check_loop(orchestrator.paper_engine))

    # BTC 5M dedicated module — Dual Parallel Instances
    from app.btc5m.engine import btc5m_engine, btc5m_engine_2
    await btc5m_engine.start()
    await btc5m_engine_2.start()
    
    yield
    # Teardown
    logger.info("FastAPI lifecycle end.")

app = FastAPI(title="Polymarket Bot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(markets_router, prefix="/api/markets", tags=["markets"])
app.include_router(signals_router, prefix="/api/signals", tags=["signals"])
app.include_router(btc5m_router, prefix="/api/btc5m", tags=["btc5m"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(health_router, prefix="/api/health", tags=["health"])
app.include_router(system_router, prefix="/api/system", tags=["system"])
app.include_router(api_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")



@app.get("/api/status")
async def get_status():
    from app.config import settings
    return {
        "status": "ok", 
        "mode": "paper",
        "live_trading_enabled": settings.live_trading_enabled,
        "execution_mode": settings.execution_mode
    }

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
