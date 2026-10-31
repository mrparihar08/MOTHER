"""
FastAPI Application for Finance Microservice (Port 8002).
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.finance_service.database import engine, Base
from services.finance_service.routes import router as finance_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Finance Microservice",
    description="Income, Expense, Budget, and Analytics Service",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(finance_router, prefix="/api/finance", tags=["Finance"])
app.include_router(finance_router, tags=["Finance Root"])


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "finance_service",
        "port": 8002,
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8002, reload=True)
