from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.items import router as items_router
from app.routers.teams import router as teams_router

app = FastAPI(
    title="Operations Under Pressure API",
    version="0.1.0",
    description="Team-scoped operational work management API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(items_router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health", tags=["system"])
async def api_health() -> dict[str, str]:
    return {"status": "ok"}
