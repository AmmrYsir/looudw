from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from loouwd.core.config import settings
from loouwd.core.logging import logger
from loouwd.core.context import default_context
from loouwd import adapters  # Triggers auto-registration of all adapters into registry
from loouwd.core.registry import registry
from loouwd.api.v1.routes import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Loaded {len(registry.list_sources())} source adapters into registry.")
    yield
    logger.info("Shutting down loouwd API background tasks and closing HTTP client connection pool...")
    await default_context.aclose()


from loouwd.core.rate_limit import RateLimitMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Ultra-fast production-grade FastAPI Source Adapter Registry",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.get("/", response_class=ORJSONResponse)
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "active_adapters": [manifest.id for manifest in registry.list_manifests()],
        "docs_url": "/docs",
    }


def main():
    import uvicorn
    uvicorn.run(
        "loouwd.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()
