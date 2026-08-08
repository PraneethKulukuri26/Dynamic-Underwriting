"""
AIDUS - AI-Driven Dynamic Underwriting System
FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import init_db, close_db
from backend.routers import consent, osint, biometrics, privacy, underwriting

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown hooks."""
    # Startup
    logger.info("=" * 60)
    logger.info("AIDUS Backend Starting...")
    logger.info(f"  Mode: {'MOCK' if settings.use_mock_data else 'PRODUCTION'}")
    logger.info(f"  Groq Model: {settings.groq_model}")
    logger.info(f"  Privacy Epsilon: {settings.default_epsilon}")
    logger.info(f"  Debug: {settings.debug}")
    logger.info("=" * 60)

    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    await close_db()
    logger.info("AIDUS Backend shut down cleanly")


# Create FastAPI application
app = FastAPI(
    title="AIDUS - AI-Driven Dynamic Underwriting System",
    description=(
        "A multi-agent, privacy-preserving underwriting engine that fuses "
        "Open Banking data, OSINT intelligence, behavioral biometrics, and "
        "Groq-powered LLM reasoning to produce dynamic credit decisions."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(consent.router)
app.include_router(osint.router)
app.include_router(biometrics.router)
app.include_router(privacy.router)
app.include_router(underwriting.router)


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker HEALTHCHECK."""
    return {
        "status": "healthy",
        "service": "AIDUS Backend",
        "version": "1.0.0",
        "mode": "MOCK" if settings.use_mock_data else "PRODUCTION",
        "model": settings.groq_model,
    }


@app.get("/")
async def root():
    """Root endpoint with API overview."""
    return {
        "service": "AIDUS - AI-Driven Dynamic Underwriting System",
        "version": "1.0.0",
        "modules": {
            "consent": "/api/v1/consent/",
            "financial": "/api/v1/financial/",
            "osint": "/api/v1/osint/",
            "biometrics": "/api/v1/biometrics/",
            "privacy": "/api/v1/privacy/",
            "underwriting": "/api/v1/underwriting/",
        },
        "docs": "/docs",
        "health": "/health",
    }
