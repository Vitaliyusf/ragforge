"""FastAPI application entry point for the memory service."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

try:
    from shared.metrics import setup_metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

from app.bootstrap.runtime import MemoryApplicationRuntime
from app.core.config import settings
from app.rest.routes import api_router
from app.utils.common import setup_cors

runtime = MemoryApplicationRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.shutdown()


app = FastAPI(title="Memory Service", lifespan=lifespan)
setup_cors(app)
if _HAS_METRICS:
    setup_metrics(app, "memory")
app.include_router(api_router, prefix="/api")


@app.get("/health")
@app.get("/live")
def live() -> dict:
    return runtime.live_payload()


@app.get("/ready")
def ready() -> JSONResponse:
    payload, is_ready = runtime.readiness_payload()
    return JSONResponse(payload, status_code=200 if is_ready else 503)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.service_host, port=settings.service_port)
