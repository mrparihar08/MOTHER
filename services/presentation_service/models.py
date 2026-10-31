"""
Presentation Studio Domain Models (Isolated schema without foreign keys to Auth or Finance DBs).
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship

from services.presentation_service.database import Base


class Presentation(Base):
    __tablename__ = "presentations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    theme = Column(String(100), default="modern")
    total_slides = Column(Integer, default=5)
    file_path = Column(String(512), nullable=True)
    cloud_url = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    slides = relationship("PresentationSlide", back_populates="presentation", cascade="all, delete-orphan")


class PresentationSlide(Base):
    __tablename__ = "presentation_slides"

    id = Column(Integer, primary_key=True, index=True)
    presentation_id = Column(Integer, ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False)
    slide_index = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    content_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    presentation = relationship("Presentation", back_populates="slides")


class PresentationJob(Base):
    __tablename__ = "presentation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    task_type = Column(String(50), nullable=False)
    status = Column(String(50), default="pending", index=True)
    progress = Column(Float, default=0.0)
    result_url = Column(String(1024), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
