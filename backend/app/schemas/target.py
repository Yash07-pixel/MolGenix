"""
Target Pydantic Schemas - Request/Response validation
"""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict


class TargetBase(BaseModel):
    """Base schema with common fields."""
    name: str = Field(..., min_length=1, max_length=256, description="Target name (e.g., BACE1, HER2)")
    uniprot_id: Optional[str] = Field(None, max_length=20, description="UniProt ID for the target")
    druggability_score: Optional[float] = Field(None, ge=0, le=1, description="Druggability score (0-1)")


class TargetCreate(TargetBase):
    """Schema for creating a new target."""
    pass


class TargetUpdate(BaseModel):
    """Schema for updating a target."""
    name: Optional[str] = None
    uniprot_id: Optional[str] = None
    druggability_score: Optional[float] = None


class TargetResponse(TargetBase):
    """Schema for returning target data."""
    id: UUID
    created_at: datetime
    chembl_id: Optional[str] = None
    target_class: Optional[str] = None
    disease: Optional[str] = None
    known_inhibitors: Optional[int] = None
    structure_count: Optional[int] = None
    pdb_id: Optional[str] = None
    gemini_source: Optional[str] = None
    druggability_breakdown: Optional[Dict[str, float]] = None
    
    class Config:
        from_attributes = True


class TargetDetailResponse(TargetResponse):
    """Schema with relationships."""
    molecules_count: int = Field(0, description="Number of molecules generated for this target")
    reports_count: int = Field(0, description="Number of reports generated for this target")
    
    class Config:
        from_attributes = True
