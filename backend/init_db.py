#!/usr/bin/env python
"""
Database initialization and verification script.

This script:
1. Creates all database tables
2. Verifies the schema
3. Can be run from CLI: python init_db.py
"""
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db, engine, SessionLocal
from app.models import Base, Target, Molecule, Report
from sqlalchemy import inspect, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize the database and create all tables."""
    logger.info("=" * 60)
    logger.info("🧬 MolGenix Database Initialization")
    logger.info("=" * 60)
    
    try:
        # Create tables
        logger.info("\n1️⃣  Creating database tables...")
        init_db()
        logger.info("✅ Tables created successfully")
        
        # Inspect and verify tables
        logger.info("\n2️⃣  Verifying database schema...")
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        logger.info(f"✅ Found {len(tables)} table(s): {', '.join(tables)}")
        
        # Print table details
        for table_name in tables:
            columns = inspector.get_columns(table_name)
            logger.info(f"\n  📊 Table: {table_name}")
            for col in columns:
                logger.info(f"     - {col['name']}: {col['type']}")
        
        # Test connection
        logger.info("\n3️⃣  Testing database connection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✅ Connection successful")
        
        # List foreign keys
        logger.info("\n4️⃣  Foreign key relationships:")
        for table_name in inspector.get_table_names():
            fks = inspector.get_foreign_keys(table_name)
            if fks:
                for fk in fks:
                    logger.info(f"  {table_name}.{fk['constrained_columns']} → {fk['referred_table']}.{fk['referred_columns']}")
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ Database initialization completed successfully!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Error during database initialization:")
        logger.error(f"   {type(e).__name__}: {e}")
        logger.error("\n💡 Troubleshooting:")
        logger.error("   1. Verify DATABASE_URL in .env file")
        logger.error("   2. Ensure PostgreSQL is running")
        logger.error("   3. Check credentials: postgres://user:password@host:port/db")
        return False


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
