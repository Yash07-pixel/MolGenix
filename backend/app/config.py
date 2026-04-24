import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://molgenix:password@localhost:5432/molgenix"
    )
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    GEMINI_RETRY_BASE_SECONDS: float = float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "2"))
    
    # External APIs
    CHEMBL_API_BASE: str = "https://www.ebi.ac.uk/chembl/api/data"
    
    # Application
    APP_NAME: str = "MolGenix"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # CORS
    ALLOWED_ORIGINS: list = ["*"]
    
    # ML Models
    DOCKING_MODEL: str = "vina"  # AutoDock Vina
    ADMET_MODEL: str = "deepchem"
    
    # Paths
    PDB_STORAGE_PATH: str = str(BASE_DIR / "data" / "pdb_files")
    CHEMBL_SEED_PATH: str = str(BASE_DIR / "data" / "chembl_seed")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
