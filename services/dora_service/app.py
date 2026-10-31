# services/dora-service/app.py
"""
Standalone DORA Clinical Intelligence Microservice.
Isolated deployment for medical knowledge retrieval & ML disease estimation.
Offloads heavy scikit-learn & SciPy compute away from the main MOTHER API server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure repo root or local path on sys.path
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.dora.engine import engine, KnowledgeEngine, DATA_PATH, TYPE_TO_SPECIALIST, DEFAULT_PRECAUTIONS, DEFAULT_TESTS

app = FastAPI(
    title="DORA Clinical Intelligence Microservice",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SymptomsRequest(BaseModel):
    symptoms: List[str] = Field(..., description="List of observed symptoms", json_schema_extra={"example": ["fever", "cough"]})
    severity: Optional[str] = Field("Moderate", json_schema_extra={"example": "Moderate"})
    top_k: int = Field(5, ge=1, le=15)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "dora-clinical-microservice",
        "total_diseases": len(engine.disease_records),
        "total_symptoms": len(engine.symptom_list),
    }


@app.get("/symptoms")
@app.get("/api/dora/symptoms")
def get_symptoms(query: Optional[str] = None):
    if query:
        q = query.lower().strip()
        filtered = [s for s in engine.symptom_list if q in s]
        return {"query": query, "count": len(filtered), "symptoms": filtered}
    return {"count": len(engine.symptom_list), "symptoms": engine.symptom_list}


@app.get("/diseases")
@app.get("/api/dora/diseases")
def get_diseases():
    return {
        "total": len(engine.disease_records),
        "diseases": [
            {
                "disease": r["Disease"],
                "type": r["Type"],
                "severity": r["Severity_Level"],
                "symptoms_count": len(r["Symptoms"]),
            }
            for r in engine.disease_records
        ],
    }


@app.post("/predict")
@app.post("/api/dora/predict")
def predict(request: SymptomsRequest):
    if not request.symptoms:
        raise HTTPException(status_code=400, detail="Symptoms list cannot be empty")

    res = engine.predict(request.symptoms, top_k=request.top_k)
    return res


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8004"))
    uvicorn.run(app, host="0.0.0.0", port=port)
