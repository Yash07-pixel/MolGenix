"""
Molecule Model - Represents a generated drug candidate molecule
"""
from sqlalchemy import Column, String, Float, Boolean, JSON, ForeignKey, UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Molecule(BaseModel):
    """
    Molecule represents a single drug candidate molecule.
    
    Stores: SMILES representation, drug-likeness scores, toxicity predictions, 
    docking affinity, and optimization status.
    """
    __tablename__ = "molecules"
    
    target_id = Column(UUID(as_uuid=True), ForeignKey("targets.id", ondelete="CASCADE"), nullable=False, index=True)
    smiles = Column(String(2048), nullable=False, index=True)
    lipinski_pass = Column(Boolean, default=False, nullable=False)
    sas_score = Column(Float, nullable=True)  # Synthetic Accessibility Score (0-10, lower is better)
    admet_scores = Column(JSON, nullable=True)  # Dict of ADMET predictions: {hepatotoxicity, herg, bbbp, bioavailability}
    docking_score = Column(Float, nullable=True)  # kcal/mol binding affinity
    is_optimized = Column(Boolean, default=False, nullable=False)
    optimization_changes = Column(JSON, nullable=True)
    
    # Relationships
    target = relationship("Target", back_populates="molecules")
    
    def __repr__(self):
        return f"<Molecule(id={self.id}, target_id={self.target_id}, lipinski_pass={self.lipinski_pass})>"
