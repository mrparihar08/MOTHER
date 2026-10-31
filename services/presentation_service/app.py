"""
FastAPI Application for Presentation Studio Microservice (Port 8005).
"""
import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.presentation_service.database import engine, Base
from backend.presentation.presentation_api import router as presentation_router

# Ensure schema
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Presentation Studio Microservice",
    description="AI Presentation Generation, PPTX/PDF Rendering, and Job Queue Service",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "presentation_service",
        "port": 8005,
    }


# Mount routes under /api/presentation and /
app.include_router(presentation_router, prefix="/api/presentation", tags=["Presentation Studio"])
app.include_router(presentation_router, tags=["Presentation Root"])


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8005"))
    uvicorn.run("services.presentation_service.app:app", host="0.0.0.0", port=port, reload=True)
