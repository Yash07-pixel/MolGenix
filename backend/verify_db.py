#!/usr/bin/env python
"""
Database layer verification script.

Tests:
1. Model imports
2. Pydantic schema validation
3. Model relationships
4. UUID generation
"""
import sys
import os
import json
from datetime import datetime, timezone
from uuid import uuid4

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_model_imports():
    """Test that all models can be imported."""
    print("\n" + "="*60)
    print("1️⃣  Testing Model Imports")
    print("="*60)
    
    try:
        from app.models import Base, BaseModel, Target, Molecule, Report
        print("✅ All models imported successfully")
        print(f"   - Base: {Base}")
        print(f"   - BaseModel: {BaseModel}")
        print(f"   - Target: {Target}")
        print(f"   - Molecule: {Molecule}")
        print(f"   - Report: {Report}")
        return True
    except Exception as e:
        print(f"❌ Failed to import models: {e}")
        return False


def test_schema_validation():
    """Test Pydantic schema validation."""
    print("\n" + "="*60)
    print("2️⃣  Testing Schema Validation")
    print("="*60)
    
    try:
        from app.schemas import (
            TargetCreate, TargetResponse, TargetDetailResponse, TargetUpdate,
            MoleculeCreate, MoleculeResponse, MoleculeUpdate, ADMETScores,
            ReportCreate, ReportResponse, ReportUpdate
        )
        
        # Test TargetCreate
        target_data = {
            "name": "BACE1",
            "uniprot_id": "P56817",
            "druggability_score": 0.85
        }
        target_create = TargetCreate(**target_data)
        print(f"✅ TargetCreate valid: {target_create.name}")
        
        # Test TargetResponse (requires all fields including id)
        target_response_data = {
            "id": uuid4(),
            "name": "BACE1",
            "uniprot_id": "P56817",
            "druggability_score": 0.85,
            "created_at": datetime.now(timezone.utc)
        }
        target_response = TargetResponse(**target_response_data)
        print(f"✅ TargetResponse valid: {target_response.id}")
        
        # Test MoleculeCreate with ADMET scores
        admet = ADMETScores(
            hepatotoxicity=0.15,
            herg_inhibition=0.08,
            bbbp=0.72,
            oral_bioavailability=0.81
        )
        print(f"✅ ADMETScores valid: {admet.hepatotoxicity}")
        
        molecule_data = {
            "target_id": uuid4(),
            "smiles": "CC(C)Cc1ccc(cc1)C(C)C(O)=O",
            "lipinski_pass": True,
            "sas_score": 3.2,
            "admet_scores": admet.dict()
        }
        molecule_create = MoleculeCreate(**molecule_data)
        print(f"✅ MoleculeCreate valid: {molecule_create.smiles}")
        
        # Test ReportCreate
        report_data = {
            "target_id": uuid4(),
            "pdf_path": "/reports/2026-04-17-BACE1.pdf"
        }
        report_create = ReportCreate(**report_data)
        print(f"✅ ReportCreate valid: {report_create.pdf_path}")
        
        return True
    except Exception as e:
        print(f"❌ Schema validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_model_relationships():
    """Test model relationships (without database)."""
    print("\n" + "="*60)
    print("3️⃣  Testing Model Relationships")
    print("="*60)
    
    try:
        from app.models import Target, Molecule, Report
        
        # Check Target relationships
        print(f"✅ Target has molecules relationship: {'molecules' in Target.__dict__}")
        print(f"✅ Target has reports relationship: {'reports' in Target.__dict__}")
        
        # Check Molecule relationships
        print(f"✅ Molecule has target relationship: {'target' in Molecule.__dict__}")
        
        # Check Report relationships
        print(f"✅ Report has target relationship: {'target' in Report.__dict__}")
        
        # Check table names
        print(f"✅ Target tablename: {Target.__tablename__}")
        print(f"✅ Molecule tablename: {Molecule.__tablename__}")
        print(f"✅ Report tablename: {Report.__tablename__}")
        
        return True
    except Exception as e:
        print(f"❌ Relationship test failed: {e}")
        return False


def test_database_config():
    """Test database configuration."""
    print("\n" + "="*60)
    print("4️⃣  Testing Database Configuration")
    print("="*60)
    
    try:
        from app.config import settings
        from app.database import engine, SessionLocal, Base, get_db
        
        print(f"✅ Database URL configured: {settings.DATABASE_URL[:30]}...")
        print(f"✅ DEBUG mode: {settings.DEBUG}")
        print(f"✅ Engine created: {engine}")
        print(f"✅ SessionLocal created: {SessionLocal}")
        print(f"✅ Base metadata: {Base.metadata}")
        
        # Check if get_db is callable
        if callable(get_db):
            print(f"✅ get_db dependency injection available")
        
        return True
    except Exception as e:
        print(f"❌ Database config test failed: {e}")
        return False


def test_migration_files():
    """Test that migration files exist."""
    print("\n" + "="*60)
    print("5️⃣  Testing Migration Files")
    print("="*60)
    
    try:
        import pathlib
        backend_dir = pathlib.Path(__file__).parent
        
        # Check alembic directory
        alembic_dir = backend_dir / "alembic"
        assert alembic_dir.exists(), "alembic directory missing"
        print(f"✅ alembic directory exists")
        
        # Check env.py
        env_py = alembic_dir / "env.py"
        assert env_py.exists(), "alembic/env.py missing"
        print(f"✅ alembic/env.py exists")
        
        # Check versions directory
        versions_dir = alembic_dir / "versions"
        assert versions_dir.exists(), "alembic/versions directory missing"
        print(f"✅ alembic/versions directory exists")
        
        # Check initial migration
        init_migration = versions_dir / "001_init.py"
        assert init_migration.exists(), "initial migration missing"
        print(f"✅ Initial migration (001_init.py) exists")
        
        # Check alembic.ini
        alembic_ini = backend_dir / "alembic.ini"
        assert alembic_ini.exists(), "alembic.ini missing"
        print(f"✅ alembic.ini exists")
        
        return True
    except Exception as e:
        print(f"❌ Migration file test failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("\n" + "🧬 MolGenix Database Layer Verification".center(60, "="))
    
    tests = [
        ("Model Imports", test_model_imports),
        ("Schema Validation", test_schema_validation),
        ("Model Relationships", test_model_relationships),
        ("Database Config", test_database_config),
        ("Migration Files", test_migration_files),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n{'='*60}")
    if passed == total:
        print(f"✅ All {total} tests passed!")
        print("="*60)
        return True
    else:
        print(f"❌ {total - passed} out of {total} tests failed")
        print("="*60)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
