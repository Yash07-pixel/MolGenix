# 🧬 MolGenix — AI-Powered Drug Discovery Backend

MolGenix is an end-to-end AI drug discovery platform where researchers describe a disease target in plain English, and the system generates, screens, and optimizes novel molecular candidates.

## Project Structure

```
molgenix/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application entry point
│   │   ├── config.py               # Configuration management
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── routers/                # FastAPI route handlers
│   │   ├── services/               # Business logic layer
│   │   ├── ml/                     # ML model wrappers (RDKit, DeepChem, etc.)
│   │   └── utils/                  # Utility functions
│   ├── data/
│   │   ├── pdb_files/              # Protein 3D structures (*.pdb)
│   │   └── chembl_seed/            # Seed SMILES from ChEMBL
│   ├── tests/                      # Test suite
│   ├── requirements.txt            # Python dependencies
│   ├── Dockerfile                  # Docker image definition
│   └── .env.example                # Environment variables template
├── docker-compose.yml              # Multi-container orchestration
└── README.md                       # This file
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Web Framework** | FastAPI |
| **Server** | Uvicorn |
| **Database** | PostgreSQL + SQLAlchemy |
| **Chemistry** | RDKit, DeepChem |
| **Docking** | AutoDock Vina (via integration) |
| **ML/ADMET** | DeepChem (pretrained models) |
| **PDF Export** | ReportLab |
| **Vector Search** | ChromaDB |
| **API Integration** | Requests, Biopython |
| **Containerization** | Docker & Docker Compose |

## Quick Start

### Local Development (No Docker)

1. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and database URL
   ```

4. **Run the development server:**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Verify health check:**
   ```bash
   curl http://localhost:8000/health
   # Expected: {"status": "ok"}
   ```

6. **Access API documentation:**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Docker Deployment

1. **Build and run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

2. **Verify the backend is running:**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Stop services:**
   ```bash
   docker-compose down
   ```

## Environment Variables

Create a `.env` file in the `backend/` directory:

```
DATABASE_URL=postgresql://molgenix:password@localhost:5432/molgenix
GEMINI_API_KEY=your_gemini_api_key_here
DEBUG=False
APP_NAME=MolGenix
APP_VERSION=0.1.0
CHEMBL_API_BASE=https://www.ebi.ac.uk/chembl/api/data
```

## API Endpoints

### Health Check
- **GET** `/health` — Returns `{"status": "ok"}`

### Root
- **GET** `/` — Returns app info and documentation links

More endpoints will be added as modules are implemented:
- Target Intelligence
- Molecule Generation
- ADMET Prediction
- Docking & Optimization
- Report Generation

## Core Modules (To Be Implemented)

1. **Module 1: Target Intelligence Engine**
   - Natural language input parsing (Gemini API)
   - Knowledge graph queries (UniProt, OMIM, STRING DB)
   - Druggability scoring

2. **Module 2: Generative Molecule Designer**
   - SMILES generation via RDKit
   - Lipinski's Rule of Five filter
   - Synthetic Accessibility Score (SAS)
   - 3D visualization

3. **Module 3: ADMET Predictor**
   - Hepatotoxicity prediction
   - hERG cardiotoxicity prediction
   - Blood-brain barrier penetration
   - Oral bioavailability scoring

4. **Module 4: Molecular Docking + Lead Optimization**
   - AutoDock Vina integration
   - Binding affinity scoring
   - R-group substitution optimization

5. **Module 5: Research Report Generator**
   - PDF export with all results
   - Gemini-written summary

## Development Workflow

1. Create feature branches
2. Write tests in `backend/tests/`
3. Implement endpoints in `backend/app/routers/`
4. Add business logic in `backend/app/services/`
5. Use ML wrappers in `backend/app/ml/`
6. Run tests: `pytest backend/tests/`

## Testing

```bash
cd backend
pytest tests/
```

## Database Setup

PostgreSQL is configured in `docker-compose.yml`. To manually initialize:

```bash
# Inside postgres container or via psql
CREATE DATABASE molgenix;
```

SQLAlchemy models will auto-create tables when defined.

## Running Tests Locally

```bash
cd backend
pytest -v tests/
```

## Deployment

The application is containerized and ready for deployment on:
- Hugging Face Spaces
- Render
- AWS ECS
- Google Cloud Run
- Any Docker-compatible platform

## Contributing

1. Clone the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Submit a pull request

## License

MIT License

## Contact

For questions or contributions, reach out to the MolGenix team.

---

**Status:** ✅ Backend scaffold complete and verified. Ready for module implementation.
