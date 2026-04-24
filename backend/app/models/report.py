"""
Report Model - Represents a generated research report PDF
"""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Report(BaseModel):
    """
    Report represents a generated PDF research report linking 
    target candidates and results.
    
    Stores: PDF file path, timestamps, and relationship to target.
    """
    __tablename__ = "reports"
    
    target_id = Column(UUID(as_uuid=True), ForeignKey("targets.id", ondelete="CASCADE"), nullable=False, index=True)
    molecule_ids = Column(JSON, nullable=True)
    pdf_path = Column(String(512), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    
    # Relationships
    target = relationship("Target", back_populates="reports")
    
    def __repr__(self):
        return f"<Report(id={self.id}, target_id={self.target_id}, pdf_path='{self.pdf_path}')>"
