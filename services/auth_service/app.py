"""
FastAPI Application for Centralized Auth & Core Service (Port 8001).
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.auth_service.database import engine, Base
from services.auth_service.routes import router as auth_router
from services.auth_service.crypto import RSAKeyManager
from shared.security.jwt_validator import JWKSKeyManager

# Ensure schema exists
Base.metadata.create_all(bind=engine)

# Pre-register local public PEM in shared JWKSKeyManager
key_mgr = RSAKeyManager.get_instance()
JWKSKeyManager.get_instance().register_public_pem(key_mgr.kid, key_mgr.public_pem)

app = FastAPI(
    title="Centralized Auth & Core Service",
    description="Identity Provider, RS256 JWT, JWKS, and User Management",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes under /api/auth and root for gateway flexibility
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(auth_router, tags=["Auth Root"])


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "auth_service",
        "port": 8001,
        "key_id": key_mgr.kid,
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
