"""
Molecule Pydantic Schemas - Request/Response validation
"""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any


class ADMETScores(BaseModel):
    """ADMET prediction scores."""
    hepatotoxicity: Optional[float] = Field(None, ge=0, le=1, description="Hepatotoxicity risk (0=safe, 1=toxic)")
    herg_inhibition: Optional[float] = Field(None, ge=0, le=1, description="hERG inhibition risk (cardiotoxicity)")
    bbbp: Optional[float] = Field(None, ge=0, le=1, description="Blood-brain barrier penetration probability")
    oral_bioavailability: Optional[float] = Field(None, ge=0, le=1, description="Oral bioavailability score")


class MoleculeBase(BaseModel):
    """Base schema with common fields."""
    smiles: str = Field(..., max_length=2048, description="SMILES representation of molecule")
    lipinski_pass: bool = Field(True, description="Passes Lipinski Rule of Five (drug-likeness)")
    sas_score: Optional[float] = Field(None, ge=0, le=10, description="Synthetic Accessibility Score")
    admet_scores: Optional[ADMETScores] = None
    docking_score: Optional[float] = Field(None, description="Binding affinity (kcal/mol)")
    is_optimized: bool = Field(False, description="Whether molecule has been optimized")


class MoleculeCreate(BaseModel):
    """Schema for creating a new molecule."""
    target_id: UUID
    smiles: str = Field(..., max_length=2048)
    lipinski_pass: bool = True
    sas_score: Optional[float] = None
    admet_scores: Optional[Dict[str, Any]] = None
    docking_score: Optional[float] = None


class MoleculeUpdate(BaseModel):
    """Schema for updating a molecule."""
    lipinski_pass: Optional[bool] = None
    sas_score: Optional[float] = None
    admet_scores: Optional[Dict[str, Any]] = None
    docking_score: Optional[float] = None
    is_optimized: Optional[bool] = None


class MoleculeResponse(MoleculeBase):
    """Schema for returning molecule data."""
    id: UUID
    target_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True


class MoleculeDetailResponse(MoleculeResponse):
    """Schema with computed fields."""
    drug_likeness_score: float = Field(0.0, description="Composite drug-likeness metric")
    
    class Config:
        from_attributes = True
