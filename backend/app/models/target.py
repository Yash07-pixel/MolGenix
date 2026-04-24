"""
Target Model - Represents a disease/protein target for drug discovery
"""
from sqlalchemy import Boolean, Column, Float, JSON, String
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Target(BaseModel):
    """
    Target represents a protein or disease target for drug discovery.
    
    Example: BACE1 (Alzheimer's target), HER2 (Cancer target)
    """
    __tablename__ = "targets"
    
    name = Column(String(256), nullable=False, index=True)
    uniprot_id = Column(String(20), nullable=True, unique=True, index=True)
    druggability_score = Column(Float, nullable=True)
    chembl_id = Column(String(64), nullable=True)
    target_class = Column(String(64), nullable=True)
    disease = Column(String(256), nullable=True)
    pdb_id = Column(String(32), nullable=True)
    known_inhibitors = Column(JSON, nullable=True)
    function = Column(String, nullable=True)
    druggability_breakdown = Column(JSON, nullable=True)
    pipeline_complete = Column(Boolean, nullable=False, default=False)
    pipeline_error = Column(String, nullable=True)
    
    # Relationships
    molecules = relationship("Molecule", back_populates="target", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="target", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Target(id={self.id}, name='{self.name}', uniprot_id='{self.uniprot_id}')>"
