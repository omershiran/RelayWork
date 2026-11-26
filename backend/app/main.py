from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .api import api
from .auth import redis
from .db import engine
from .mcp import server
from .orders import router as order_router
from .negotiations import router as negotiations_router
from .messaging import router as messaging_router
from .work import router as work_router

mcp_app = server.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
    async with server.session_manager.run():
        yield


app = FastAPI(title="agentrelai", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
              redoc_url=None, openapi_url="/api/openapi.json")
@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "invalid_input", "fields": [
            {"location": error["loc"], "type": error["type"]} for error in exc.errors()
        ]},
        headers={"Cache-Control": "no-store"},
    )


app.include_router(api)
app.include_router(work_router)
app.include_router(messaging_router)
app.include_router(order_router)
app.include_router(negotiations_router)
app.mount("/mcp", mcp_app)


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
def mcp_redirect():
    return RedirectResponse("/mcp/", status_code=307)


@app.get("/api/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1 from alembic_version"))
        redis.ping()
    except (SQLAlchemyError, RedisError) as exc:
        raise HTTPException(503, "dependency_unavailable") from exc
    return {"status": "ok"}
