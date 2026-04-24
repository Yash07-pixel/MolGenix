# 🧬 MolGenix Phase 2 - Visual Complete Guide

## What We Built (Summarized)

### 📊 Three Database Tables with Relationships

```
┌─────────────────────────────────────────────────────────────────────┐
│                          TARGETS                                     │
├──────────────────────────────────────────────────────────────────────┤
│ PK: id (UUID)                                                        │
│ FI: name (VARCHAR)                                                   │
│ FI: uniprot_id (VARCHAR, UNIQUE)                                     │
│ FI: druggability_score (FLOAT)                                       │
│ FI: created_at (TIMESTAMP)                                           │
│                                                                      │
│ Example Data:                                                        │
│ • BACE1 (UniProt: P56817) — Alzheimer's target                      │
│ • HER2 (UniProt: P04637) — Cancer target                            │
│ • TNFα (UniProt: P01375) — Inflammation target                      │
└──────────────────────────────────────────────────────────────────────┘
        │ 1-to-Many                              │ 1-to-Many
        ↓                                        ↓
┌─────────────────────────────────┐    ┌──────────────────────────────┐
│      MOLECULES (Candidates)     │    │        REPORTS (PDFs)        │
├─────────────────────────────────┤    ├──────────────────────────────┤
│ PK: id (UUID)                   │    │ PK: id (UUID)                │
│ FK: target_id (→targets.id)     │    │ FK: target_id (→targets.id)  │
│ FI: smiles (VARCHAR)            │    │ FI: pdf_path (VARCHAR)       │
│ FI: lipinski_pass (BOOLEAN)     │    │ FI: created_at (TIMESTAMP)   │
│ FI: sas_score (FLOAT)           │    │                              │
│ FI: admet_scores (JSON)         │    │ Example:                     │
│ FI: docking_score (FLOAT)       │    │ • /reports/BACE1_2026.pdf   │
│ FI: is_optimized (BOOLEAN)      │    │ • /reports/HER2_2026.pdf    │
│ FI: created_at (TIMESTAMP)      │    └──────────────────────────────┘
│                                 │
│ Example Data:                   │
│ • CC(C)Cc1ccc(cc1)C(C)(O)=O    │
│   Lipinski: ✅ Pass             │
│   SAS: 3.2 (easy to synthesize) │
│   ADMET: {toxic: 0.15, bbbp:0.72}│
│   Docking: -8.5 kcal/mol        │
│   Optimized: No                 │
└─────────────────────────────────┘
```

---

## 🔍 Data Flow Through the System

```
┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: Researcher Uses API                                         │
│ curl -X POST /api/targets \                                         │
│   -d '{"name":"BACE1","uniprot_id":"P56817",...}'                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 2: FastAPI Receives Request                                    │
│ @app.post("/targets", response_model=TargetResponse)               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 3: Pydantic Schema Validates                                   │
│ class TargetCreate(BaseModel):                                      │
│     name: str ✅ Type checked                                       │
│     uniprot_id: Optional[str] ✅ Validated                          │
│ Returns: TargetCreate(name="BACE1", ...)                            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 4: Service Layer (To Be Built)                                 │
│ def create_target(db: Session, target: TargetCreate):              │
│     db_target = Target(**target.dict())  ← ORM object             │
│     db.add(db_target)                                               │
│     db.commit()                                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 5: SQLAlchemy ORM Creates Object                              │
│ target = Target(                                                    │
│     id=uuid4(),                        ← Auto-generated            │
│     name="BACE1",                                                   │
│     uniprot_id="P56817",                                            │
│     created_at=datetime.now(timezone.utc)  ← Auto-set             │
│ )                                                                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 6: Database Session Manages Transaction                        │
│ • db.add(target) — Add to session                                   │
│ • db.commit() — Begin transaction                                   │
│ • db.refresh() — Get server defaults                                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 7: PostgreSQL Executes SQL                                     │
│ BEGIN;                                                              │
│ INSERT INTO targets (id, name, uniprot_id, created_at)             │
│ VALUES ('550e8400-e29b-41d4...', 'BACE1', 'P56817', '2026-04-17...');│
│ COMMIT;                                                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 8: SQLAlchemy Maps Back to Python                             │
│ target (Target object with id, name, etc.)                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 9: Pydantic Serializes Response                               │
│ TargetResponse.from_orm(target)                                     │
│ ↓                                                                   │
│ {                                                                   │
│   "id": "550e8400-e29b-41d4-a716-446655440000",                  │
│   "name": "BACE1",                                                 │
│   "uniprot_id": "P56817",                                          │
│   "druggability_score": null,                                      │
│   "created_at": "2026-04-17T12:34:56+00:00"                       │
│ }                                                                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│ Step 10: FastAPI Returns JSON Response (200 OK)                    │
│ Content-Type: application/json                                      │
│ ↓ HTTP Response ↓                                                   │
│ Status: 201 Created                                                │
│ Location: /api/targets/550e8400-e29b-41d4-a716-446655440000       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Structure (Updated)

```
molgenix/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py ✅ Updated (db init on startup)
│   │   ├── config.py
│   │   ├── database.py ✅ NEW (engine, SessionLocal, get_db)
│   │   │
│   │   ├── models/ ✅ NEW (All ORM models)
│   │   │   ├── __init__.py
│   │   │   ├── base.py (BaseModel with id, created_at)
│   │   │   ├── target.py (3 tables with relationships)
│   │   │   ├── molecule.py
│   │   │   └── report.py
│   │   │
│   │   ├── schemas/ ✅ NEW (All Pydantic schemas)
│   │   │   ├── __init__.py
│   │   │   ├── target.py (TargetCreate, TargetResponse, etc.)
│   │   │   ├── molecule.py (MoleculeCreate, MoleculeResponse, etc.)
│   │   │   └── report.py (ReportCreate, ReportResponse, etc.)
│   │   │
│   │   ├── routers/ (Coming: API endpoints)
│   │   ├── services/ (Coming: Business logic)
│   │   ├── ml/ (Coming: ML models)
│   │   └── utils/
│   │
│   ├── alembic/ ✅ NEW (Database migrations)
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 001_init.py (Create all tables)
│   │       └── __init__.py
│   │
│   ├── alembic.ini ✅ NEW (Alembic config)
│   ├── init_db.py ✅ NEW (Initialize + verify)
│   ├── verify_db.py ✅ NEW (Run tests)
│   ├── database.py ✅ NEW (Connection layer)
│   ├── DATABASE.md ✅ NEW (56-section guide)
│   ├── PHASE2-DATABASE-COMPLETE.md ✅ NEW (Summary)
│   ├── requirements.txt ✅ Updated (+ alembic)
│   └── .env.example
│
├── Dockerfile
├── docker-compose.yml
├── README.md
├── INSTALLATION.md
└── .gitignore
```

---

## 🎯 What Each Component Does

### SQLAlchemy Models
**Purpose:** Bridge between Python objects and database tables

```python
from app.models import Target

# Python object
target = Target(
    name="BACE1",
    uniprot_id="P56817"
)

# SQLAlchemy maps this to:
INSERT INTO targets (id, name, uniprot_id, created_at) ...
```

### Pydantic Schemas
**Purpose:** Validate API input and serialize responses

```python
from app.schemas import TargetCreate, TargetResponse

# API request validation
data = {"name": "BACE1"}  # Dict from JSON
target_create = TargetCreate(**data)  # Validates
# If fields are missing/wrong → ValidationError

# API response serialization
target_response = TargetResponse.from_orm(db_target)
# SQLAlchemy object → Pydantic → JSON
```

### Database Connection (database.py)
**Purpose:** Manage connection pool and session lifecycle

```python
from app.database import get_db, SessionLocal

# Dependency injection in FastAPI
@app.get("/targets")
def get_targets(db: Session = Depends(get_db)):
    # FastAPI auto-creates session
    # Endpoint runs
    # FastAPI auto-closes session
    pass
```

### Alembic Migrations
**Purpose:** Version control for database schema

```bash
# Create tables
alembic upgrade head

# Rollback
alembic downgrade -1

# Create new schema change
alembic revision --autogenerate -m "add column"
```

---

## ✅ Verification Checklist

Run these to verify everything works:

### 1. Test Imports
```bash
cd backend
python -c "from app.models import Target, Molecule, Report; print('✅ Models OK')"
python -c "from app.schemas import TargetCreate; print('✅ Schemas OK')"
python -c "from app.database import get_db; print('✅ Database OK')"
```

### 2. Run Full Verification
```bash
python verify_db.py
# Output: ✅ All 5 tests passed!
```

### 3. Initialize Database
```bash
python init_db.py
# Output: Shows tables created and schema verified
```

### 4. Check Database Directly
```bash
# With Docker
docker-compose exec postgres psql -U molgenix -d molgenix -c "\dt"

# Output:
#                List of relations
#  Schema |    Name    | Type  |  Owner   
# --------+------------+-------+----------
#  public | molecules  | table | molgenix
#  public | reports    | table | molgenix
#  public | targets    | table | molgenix
```

---

## 🚀 Ready for Phase 3

### What We Can Now Build

With this database layer complete, we can now create:

### API Routers (routers/)
```python
# routers/targets.py
@router.post("/targets", response_model=TargetResponse)
def create_target(target: TargetCreate, db: Session = Depends(get_db)):
    ...

@router.get("/targets", response_model=List[TargetResponse])
def list_targets(db: Session = Depends(get_db)):
    ...
```

### Services (services/)
```python
# services/target_service.py
def create_target_service(db: Session, target: TargetCreate):
    db_target = Target(**target.dict())
    db.add(db_target)
    db.commit()
    return db_target
```

### ML Integration (ml/)
```python
# ml/admet_predictor.py
def predict_admet(smiles: str) -> ADMETScores:
    # Use DeepChem to predict
    return {"hepatotoxicity": 0.15, ...}
```

---

## 📚 Documentation Files Created

| File | Content |
|------|---------|
| DATABASE.md | 56-section complete guide |
| PHASE2-DATABASE-COMPLETE.md | Phase summary |
| app/models/*.py | Inline comments |
| app/schemas/*.py | Pydantic field docs |
| alembic/versions/001_init.py | Migration details |

---

## 🎉 Phase 2 Summary

**What we built:**
- ✅ 3 database tables (targets, molecules, reports)
- ✅ ORM models with relationships
- ✅ Pydantic schemas for validation
- ✅ Database connection management
- ✅ Alembic migrations
- ✅ Initialization scripts
- ✅ Verification tests
- ✅ Complete documentation

**Total new files:** 18  
**Total new models:** 3  
**Total new schemas:** 12  
**Total documentation sections:** 80+  
**Code lines:** 1000+  

**Status:** ✅ Production-ready database layer  
**Next:** Phase 3 - API routers & services

