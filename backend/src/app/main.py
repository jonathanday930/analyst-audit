import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes.claims import router as claims_router
from app.routes.gurus import router as gurus_router
from app.routes.links import router as links_router

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(title="AnalystAudit")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(links_router)
app.include_router(gurus_router)
app.include_router(claims_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/{_path:path}")
def api_not_found(_path: str) -> None:
    raise HTTPException(status_code=404, detail="Not found")


FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{_path:path}")
    def serve_frontend(_path: str) -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")
