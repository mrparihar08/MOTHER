from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResultCategory(str, Enum):
    NEWS = "news"
    SHOPPING = "shopping"
    EDUCATION = "education"
    RESEARCH = "research"
    GOVERNMENT = "government"
    WEB_SEARCH = "web_search"


class ShoppingMetadata(BaseModel):
    price: Optional[float] = None
    original_price: Optional[float] = None
    currency: str = "INR"
    store: str = "Amazon"  # Amazon, Flipkart, Official Store
    availability: Optional[str] = None  # "In Stock", "Available", "Pre-order"
    affiliate_url: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None


class AcademicMetadata(BaseModel):
    authors: List[str] = Field(default_factory=list)
    journal_or_venue: Optional[str] = None
    doi: Optional[str] = None
    pdf_url: Optional[str] = None
    year: Optional[int] = None
    open_access: bool = True


class EducationMetadata(BaseModel):
    platform: str = "Technical Docs"  # FastAPI Docs, Python Docs, MDN, MIT OCW, freeCodeCamp
    difficulty: Optional[str] = "All Levels"  # Beginner, Intermediate, Advanced
    is_free: bool = True
    resource_type: str = "Documentation"  # Documentation, Course, Tutorial, Reference


class GovernmentMetadata(BaseModel):
    portal: str = "Open Government Data"  # Data.gov.in, Data.gov, World Bank
    department: Optional[str] = None
    dataset_id: Optional[str] = None
    license_name: str = "Open Data License"


class StandardizedResult(BaseModel):
    id: str
    category: ResultCategory
    title: str
    description: str
    source: str
    source_domain: str
    url: str
    image: Optional[str] = None
    published_at: Optional[str] = None
    retrieved_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    attribution: Optional[str] = None
    
    # Specific metadata payloads
    shopping: Optional[ShoppingMetadata] = None
    academic: Optional[AcademicMetadata] = None
    education: Optional[EducationMetadata] = None
    government: Optional[GovernmentMetadata] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict dropping None values for clean JSON output."""
        return self.model_dump(exclude_none=True)
