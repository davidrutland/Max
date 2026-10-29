from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.database import init_db, SessionLocal
from app.artifact_store import reconcile
from app.routers import servers, chats, config, extract, auth, users, mcp, search, router_control, artifacts
from app.tools import mcp_client
from app.context_startup import context_owner_lifespan


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Was @app.on_event("startup") (deprecated); MCP needs an async startup hook anyway.
    init_db()
    with SessionLocal() as db:
        reconcile(db)
    # Connect to the configured MCP servers and register their tools. Best effort: an
    # unreachable server must not stop the app from booting.
    await mcp_client.sync_all()
    async with context_owner_lifespan():
        yield


app = FastAPI(title="Calivi", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,  # for the httpOnly session cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(servers.router)
app.include_router(chats.router)
app.include_router(config.router)
app.include_router(extract.router)
app.include_router(mcp.router)
app.include_router(search.router)
app.include_router(router_control.router)
app.include_router(artifacts.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
