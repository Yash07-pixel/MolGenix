"""
Report Pydantic Schemas - Request/Response validation
"""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class ReportBase(BaseModel):
    """Base schema with common fields."""
    pdf_path: str = Field(..., max_length=512, description="Path to generated PDF file")


class ReportCreate(BaseModel):
    """Schema for creating a new report."""
    target_id: UUID
    pdf_path: str = Field(..., max_length=512)


class ReportUpdate(BaseModel):
    """Schema for updating a report."""
    pdf_path: Optional[str] = None


class ReportResponse(ReportBase):
    """Schema for returning report data."""
    id: UUID
    target_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True


class ReportDetailResponse(ReportResponse):
    """Schema with computed fields."""
    target_name: Optional[str] = Field(None, description="Name of associated target")
    molecule_count: int = Field(0, description="Number of molecules in report")
    
    class Config:
        from_attributes = True
