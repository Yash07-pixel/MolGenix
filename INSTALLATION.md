# 🚀 MolGenix Installation Guide

## Scaffold Status: ✅ COMPLETE

The full project scaffold has been created with:
- ✅ Directory structure (backend, app, models, schemas, routers, services, ml, utils)
- ✅ FastAPI main application with health check endpoint
- ✅ Configuration management with .env support
- ✅ CORS middleware enabled
- ✅ Docker and Docker Compose setup
- ✅ Complete requirements files (full production + test variant)
- ✅ README and documentation

---

## Installation Steps (Windows)

### Option 1: Using Docker Compose (Recommended for Full Setup)

This handles all dependencies including RDKit and PostgreSQL automatically:

```bash
cd c:\Users\Dell\nmit\molgenix
docker-compose up --build
```

Then verify:
```bash
curl http://localhost:8000/health
# Expected response: {"status": "ok"}
```

### Option 2: Local Development (Python 3.13+)

**For Windows, follow these steps carefully:**

1. **Navigate to backend directory:**
   ```bash
   cd c:\Users\Dell\nmit\molgenix\backend
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Upgrade pip (critical for Windows):**
   ```bash
   python -m pip install --upgrade pip setuptools wheel
   ```

4. **Install FastAPI dependencies first (lightweight):**
   ```bash
   pip install fastapi uvicorn pydantic pydantic-settings python-dotenv
   ```

5. **Verify FastAPI works:**
   ```bash
   uvicorn app.main:app --reload
   ```
   
   Open browser: http://localhost:8000/health
   Should see: `{"status": "ok"}`

6. **Install chemistry dependencies (takes longer):**
   ```bash
   pip install rdkit-pypi deepchem reportlab chromadb requests biopython
   ```

7. **Install database dependencies:**
   ```bash
   pip install sqlalchemy psycopg2-binary
   ```

### Option 3: Using Conda (Recommended for Chemistry Packages)

Conda handles binary dependencies better:

```bash
# Create environment
conda create -n molgenix python=3.13
conda activate molgenix

# Navigate to backend
cd c:\Users\Dell\nmit\molgenix\backend

# Install from conda channels (RDKit installs better via conda)
conda install -c conda-forge rdkit deepchem

# Then install remaining via pip
pip install -r requirements.txt
```

---

## Troubleshooting Windows Installation

### Issue: `psycopg2-binary` fails to build

**Solution 1:** Use pre-built wheel (recommended)
```bash
pip install psycopg2-binary==2.9.9 --only-binary :all:
```

**Solution 2:** Use PostgreSQL-only in Docker, skip local installation
- Just use Docker Compose instead

### Issue: RDKit won't install

**Solution:** Use Conda channel
```bash
conda install -c conda-forge rdkit
```

Or skip local RDKit for now and use Docker.

### Issue: pip timeout on slow connection

```bash
pip install -r requirements.txt --default-timeout=1000
```

---

## Project Structure Verification

```
✅ molgenix/
  ✅ backend/
    ✅ app/
      ✅ main.py                 # FastAPI entry point
      ✅ config.py               # .env configuration
      ✅ models/                 # SQLAlchemy models (empty, ready for implementation)
      ✅ schemas/                # Pydantic DTO schemas (empty, ready)
      ✅ routers/                # API route handlers (empty, ready)
      ✅ services/               # Business logic layer (empty, ready)
      ✅ ml/                     # ML wrappers (empty, ready)
      ✅ utils/                  # Helpers (empty, ready)
    ✅ data/
      ✅ pdb_files/              # For .pdb protein structures
      ✅ chembl_seed/            # For ChEMBL SMILES data
    ✅ tests/                    # Test directory (ready)
    ✅ requirements.txt          # Full production dependencies
    ✅ requirements-test.txt     # Lightweight FastAPI-only
    ✅ .env.example              # Template
  ✅ Dockerfile                  # Docker image build
  ✅ docker-compose.yml          # PostgreSQL + Backend orchestration
  ✅ README.md                   # Project documentation
  ✅ .gitignore                  # Git ignore rules
```

---

## Next Steps

1. **Install dependencies** (choose an option above)

2. **Run FastAPI development server:**
   ```bash
   cd backend
   venv\Scripts\activate  # Windows
   uvicorn app.main:app --reload
   ```

3. **Access documentation:**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc
   - Health: http://localhost:8000/health

4. **Create .env file in backend/:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your API keys
   ```

5. **Ready for module implementation:** Once this is running, you can start implementing:
   - Module 1: Target Intelligence (routers/targets.py)
   - Module 2: Molecule Generation (services/molecule_generator.py)
   - Module 3: ADMET Prediction (ml/admet_predictor.py)
   - Module 4: Docking (ml/docking_engine.py)
   - Module 5: Report Generation (services/report_generator.py)

---

## Docker Quick Commands

```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f backend

# Run just the backend container
docker-compose up backend

# Clean up volumes
docker-compose down -v
```

---

## Environment Variables

Key variables in `.env`:

```
DATABASE_URL=postgresql://molgenix:password@postgres:5432/molgenix
GEMINI_API_KEY=your_key_here
DEBUG=False
```

Get your Gemini API key from: https://aistudio.google.com/app/apikey

---

## Verification Commands

```bash
# Test FastAPI is running
curl http://localhost:8000/health

# Check API docs
curl http://localhost:8000/

# Verify imports can load (minimal test)
python -c "from app.config import settings; print('Config OK')"
python -c "from app.main import app; print('Main OK')"
```

---

## Health Check Endpoint

**GET** `/health`

Response:
```json
{
  "status": "ok"
}
```

This endpoint requires NO dependencies except `fastapi` and `uvicorn`.

---

## Support

If you encounter issues:

1. **Check Python version:** `python --version` (should be 3.10+)
2. **Use Docker** if local installation fails
3. **Update pip:** `pip install --upgrade pip`
4. **Check requirements versions** at: https://pypi.org/

