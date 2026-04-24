# MolGenix Database Layer - Complete Documentation

## Overview

The database layer is built with **SQLAlchemy ORM** + **PostgreSQL** + **Alembic migrations**.

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Endpoints                           │
├─────────────────────────────────────────────────────────────────┤
│                     Pydantic Schemas                            │
│         (TargetCreate, MoleculeResponse, etc.)                  │
├─────────────────────────────────────────────────────────────────┤
│                  SQLAlchemy Models (ORM)                        │
│           (Target, Molecule, Report classes)                    │
├─────────────────────────────────────────────────────────────────┤
│                   database.py Management                        │
│         (Engine, SessionLocal, get_db dependency)               │
├─────────────────────────────────────────────────────────────────┤
│                     PostgreSQL Database                         │
│            (targets, molecules, reports tables)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### 1. targets
Represents a drug discovery target (protein or disease).

```sql
CREATE TABLE targets (
    id UUID PRIMARY KEY,
    name VARCHAR(256) NOT NULL INDEXED,
    uniprot_id VARCHAR(20) UNIQUE INDEXED,
    druggability_score FLOAT,
    created_at TIMESTAMP WITH TIMEZONE NOT NULL
);
```

**Fields:**
- `id`: Unique identifier (UUID v4)
- `name`: Target name (e.g., "BACE1", "HER2")
- `uniprot_id`: UniProt database identifier (e.g., "P56817")
- `druggability_score`: Computed score 0-1 (how easy to drug)
- `created_at`: Timestamp creation time (auto-set)

**Relationships:**
- ✅ 1→Many: targets → molecules (OnDelete: CASCADE)
- ✅ 1→Many: targets → reports (OnDelete: CASCADE)

---

### 2. molecules
Represents a generated drug candidate molecule.

```sql
CREATE TABLE molecules (
    id UUID PRIMARY KEY,
    target_id UUID NOT NULL FOREIGN KEY REFERENCES targets(id) ON DELETE CASCADE INDEXED,
    smiles VARCHAR(2048) NOT NULL INDEXED,
    lipinski_pass BOOLEAN NOT NULL,
    sas_score FLOAT,
    admet_scores JSON,
    docking_score FLOAT,
    is_optimized BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIMEZONE NOT NULL
);
```

**Fields:**
- `id`: Unique identifier (UUID v4)
- `target_id`: Foreign key to targets table
- `smiles`: SMILES string (chemical notation)
- `lipinski_pass`: Did it pass Lipinski's Rule of Five?
- `sas_score`: Synthetic Accessibility Score (0-10, lower = easier to make)
- `admet_scores`: JSON dict of predictions
  ```json
  {
    "hepatotoxicity": 0.15,
    "herg_inhibition": 0.08,
    "bbbp": 0.72,
    "oral_bioavailability": 0.81
  }
  ```
- `docking_score`: Binding affinity (kcal/mol, lower = better)
- `is_optimized`: Was this molecule optimized?
- `created_at`: Timestamp creation time

**Relationships:**
- ✅ Many→1: molecules → targets

---

### 3. reports
Represents a generated research report PDF.

```sql
CREATE TABLE reports (
    id UUID PRIMARY KEY,
    target_id UUID NOT NULL FOREIGN KEY REFERENCES targets(id) ON DELETE CASCADE INDEXED,
    pdf_path VARCHAR(512) NOT NULL,
    created_at TIMESTAMP WITH TIMEZONE NOT NULL
);
```

**Fields:**
- `id`: Unique identifier (UUID v4)
- `target_id`: Foreign key to targets table
- `pdf_path`: File system path to PDF (e.g., `/reports/2026-04-17-BACE1.pdf`)
- `created_at`: Timestamp creation time

**Relationships:**
- ✅ Many→1: reports → targets

---

## Project Structure

```
backend/
├── app/
│   ├── models/
│   │   ├── __init__.py           ← Exports Base, BaseModel, Target, Molecule, Report
│   │   ├── base.py               ← Base class with id + created_at
│   │   ├── target.py             ← Target ORM model
│   │   ├── molecule.py           ← Molecule ORM model
│   │   └── report.py             ← Report ORM model
│   ├── schemas/
│   │   ├── __init__.py           ← Exports all Pydantic schemas
│   │   ├── target.py             ← TargetCreate, TargetResponse, etc.
│   │   ├── molecule.py           ← MoleculeCreate, MoleculeResponse, etc.
│   │   └── report.py             ← ReportCreate, ReportResponse, etc.
│   ├── database.py               ← Engine, SessionLocal, get_db()
│   └── main.py                   ← FastAPI app with db initialization
├── alembic/
│   ├── env.py                    ← Alembic runtime environment
│   ├── script.py.mako            ← Migration template
│   └── versions/
│       ├── 001_init.py           ← Initial migration (create tables)
│       └── __init__.py
├── alembic.ini                   ← Alembic configuration
├── init_db.py                    ← Database initialization script
└── requirements.txt              ← Includes SQLAlchemy, Alembic, psycopg2
```

---

## How to Use

### 1. Initialize Database Tables

**Option A: Automatic (on app startup)**
```bash
cd backend
uvicorn app.main:app --reload
# Tables auto-create on startup via lifespan event
```

**Option B: Manual initialization script**
```bash
cd backend
python init_db.py
# Output shows created tables and schema verification
```

### 2. Using SQLAlchemy Models in Services

```python
from sqlalchemy.orm import Session
from app.models import Target, Molecule
from app.database import get_db

# Example service function
def create_target(db: Session, name: str, uniprot_id: str):
    target = Target(name=name, uniprot_id=uniprot_id)
    db.add(target)
    db.commit()
    db.refresh(target)
    return target

def query_targets(db: Session):
    return db.query(Target).all()

def get_molecules_for_target(db: Session, target_id: uuid.UUID):
    return db.query(Molecule).filter(Molecule.target_id == target_id).all()
```

### 3. Using in FastAPI Endpoints

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import TargetCreate, TargetResponse
from app.models import Target

router = APIRouter(prefix="/targets", tags=["targets"])

@router.post("/", response_model=TargetResponse)
def create_target(target: TargetCreate, db: Session = Depends(get_db)):
    db_target = Target(**target.dict())
    db.add(db_target)
    db.commit()
    db.refresh(db_target)
    return db_target

@router.get("/", response_model=list[TargetResponse])
def list_targets(db: Session = Depends(get_db)):
    return db.query(Target).all()
```

### 4. Pydantic Schema Validation

```python
# Request validation (incoming API call)
from app.schemas import TargetCreate

payload = {
    "name": "BACE1",
    "uniprot_id": "P56817"
}
target_in = TargetCreate(**payload)  # Validates automatically
# ✅ If valid: returns TargetCreate instance
# ❌ If invalid: raises validation error with details

# Response serialization (outgoing API response)
from app.schemas import TargetResponse

target_response = TargetResponse.from_orm(db_target)
# Converts SQLAlchemy object → Pydantic dict → JSON
```

---

## Database Migrations with Alembic

### What is Alembic?
Alembic tracks database schema changes over time (like Git for databases). Each migration is a Python script that can be applied or rolled back.

### Current Migrations

| Revision | Description |
|----------|-------------|
| `001_init` | Create targets, molecules, reports tables with indices |

### Run Migrations

**Apply migration (upgrade)**
```bash
cd backend
alembic upgrade head
# Creates all tables in the database
```

**Revert migration (downgrade)**
```bash
alembic downgrade -1
# Drops all tables in the database
```

### Create New Migration

```bash
cd backend
alembic revision --autogenerate -m "Add field to target"
# Generates new migration file in alembic/versions/
alembic upgrade head
# Apply the new migration
```

---

## Pydantic Schemas Explained

### Request Schemas (Create/Update)
```python
class TargetCreate(BaseModel):
    name: str
    uniprot_id: Optional[str] = None
    druggability_score: Optional[float] = None
```
**Use:** In `@app.post()` and `@app.put()` endpoints to validate incoming data.

### Response Schemas
```python
class TargetResponse(TargetBase):
    id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True  # Allows SQLAlchemy → Pydantic conversion
```
**Use:** In endpoint return types to validate outgoing data and auto-generate OpenAPI docs.

### Why Both?
- **Type Safety**: Catch errors before database writes
- **Documentation**: OpenAPI/Swagger auto-generated from schemas
- **Security**: Cannot accidentally return secrets (schema controls what's exposed)
- **Validation**: Min/max lengths, formats, ranges enforced

---

## Dependencies Breakdown

| Package | Purpose |
|---------|---------|
| `sqlalchemy==2.0.23` | ORM for database interactions |
| `psycopg2-binary==2.9.9` | PostgreSQL driver for Python |
| `pydantic==2.5.0` | Data validation & serialization |
| `alembic==1.12.1` | Database migrations |

---

## Testing the Database Layer

### 1. Test Model Imports
```bash
cd backend
python -c "from app.models import Target, Molecule, Report; print('✅ Models load successfully')"
```

### 2. Test Schema Validation
```bash
python -c "
from app.schemas import TargetCreate
target = TargetCreate(name='BACE1', uniprot_id='P56817')
print(f'✅ Schema valid: {target}')
"
```

### 3. Test Database Connection
```bash
python init_db.py
# Shows table creation and schema verification
```

### 4. Test with Docker Compose
```bash
docker-compose up
# Waits for PostgreSQL → Initializes FastAPI → Creates tables
```

---

## Common Errors & Solutions

### Error: "No module named 'psycopg2'"
**Solution:**
```bash
pip install psycopg2-binary
# Or use Docker Compose (auto-installs)
```

### Error: "could not translate host name 'postgres' to address"
**Solution:** You're not using Docker. Set `DATABASE_URL` to local PostgreSQL:
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/molgenix python init_db.py
```

### Error: "FATAL: database 'molgenix' does not exist"
**Solution:** Create the database first:
```bash
psql -U postgres -c "CREATE DATABASE molgenix;"
```

### Error: "relation 'targets' does not exist"
**Solution:** Run migrations:
```bash
python init_db.py
# Or use Docker Compose
docker-compose up
```

---

## Next Steps

1. ✅ **Database layer complete**
2. 🔨 **Create routers** (endpoints for CRUD operations)
3. 🔨 **Create services** (business logic)
4. 🔨 **Implement ML modules** (docking, ADMET, generation)
5. 🔨 **Add authentication** (API keys, rate limits)

---

## Quick Reference - Database Operations

```python
from sqlalchemy.orm import Session
from app.models import Target, Molecule
from app.database import SessionLocal

db = SessionLocal()

# CREATE
new_target = Target(name="BACE1", uniprot_id="P56817")
db.add(new_target)
db.commit()

# READ
target = db.query(Target).filter_by(name="BACE1").first()
all_targets = db.query(Target).all()

# UPDATE
target.druggability_score = 0.85
db.commit()

# DELETE
db.delete(target)
db.commit()

# JOIN (target with its molecules)
molecules = db.query(Molecule).filter_by(target_id=target.id).all()

db.close()
```

