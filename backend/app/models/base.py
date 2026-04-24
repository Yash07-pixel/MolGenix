"""
SQLAlchemy Base Model and Database Configuration
"""
from sqlalchemy import Column, DateTime, UUID
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone
import uuid


Base = declarative_base()


class BaseModel(Base):
    """Abstract base model with common fields for all tables."""
    __abstract__ = True
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
