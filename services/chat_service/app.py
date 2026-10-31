"""
FastAPI Application for Chat Microservice (Port 8003).
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.chat_service.database import engine, Base
from services.chat_service.routes import router as chat_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Chat Microservice",
    description="Conversational AI, Streaming SSE, and Tool-Calling Service",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(chat_router, tags=["Chat Root"])


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "chat_service",
        "port": 8003,
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8003, reload=True)
