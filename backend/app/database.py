"""
Database Configuration and Session Management
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from app.config import settings
from app.models import Base
import logging

logger = logging.getLogger(__name__)


# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Log SQL queries if DEBUG is True
    pool_pre_ping=True,  # Test connections before use
    poolclass=NullPool if settings.DATABASE_URL.startswith("sqlite") else None,  # Use NullPool for SQLite
)

# Create SessionLocal factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")


def get_db() -> Session:
    """
    Dependency injection function for FastAPI endpoints.
    
    Yields a database session that auto-closes after the request.
    
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
