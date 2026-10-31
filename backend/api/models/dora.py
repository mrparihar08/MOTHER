# backend/api/models/dora.py
"""
Dora Clinical Domain Models:
Clinical Assessments, Medical History, and Diagnosis Logs.
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float
from backend.api.database import Base
from backend.api.models.core import TimestampMixin


class DoraAssessment(Base, TimestampMixin):
    __tablename__ = "dora_assessments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    symptoms = Column(Text, nullable=False)
    predicted_disease = Column(String(200), nullable=True)
    confidence = Column(Float, default=0.0)
    urgency = Column(String(50), default="Routine")
    specialist = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)


__all__ = ["DoraAssessment"]
