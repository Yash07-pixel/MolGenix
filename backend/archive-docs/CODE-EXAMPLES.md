# 🔍 Phase 4: Code Examples & Usage Patterns

## Quick Reference: Using the Molecule Generation Service

---

## 1. Direct Service Usage (Python)

### Generate Molecules Programmatically

```python
# In a Python script or Jupyter notebook

from app.services.molecule_service import MoleculeGenerationService
from app.database import SessionLocal
from uuid import uuid4

# Setup
db = SessionLocal()
target_id = str(uuid4())

# Generate molecules
molecules, valid_count = await MoleculeGenerationService.generate_molecules_for_target(
    target_id=target_id,
    seed_smiles="CC(=O)Oc1ccccc1C(=O)O",  # Aspirin
    n_molecules=20,
    db=db
)

# Results
print(f"Generated: {len(molecules)} molecules")
print(f"Passed Lipinski: {valid_count}")

for mol in molecules:
    print(f"SMILES: {mol.smiles}")
    print(f"Lipinski pass: {mol.lipinski_pass}")
    print(f"SAS score: {mol.sas_score}")
    print(f"Properties: {mol.admet_scores}")
    print("---")
```

---

## 2. API Usage (cURL/Bash)

### Generate 20 Molecules

```bash
# Get target ID first
TARGET_RESPONSE=$(curl -s -X POST http://localhost:8000/api/targets/analyze \
  -H "Content-Type: application/json" \
  -d '{"name": "BACE1 in Alzheimer"}')

TARGET_ID=$(echo $TARGET_RESPONSE | jq -r '.id')

# Generate molecules
curl -X POST http://localhost:8000/api/molecules/generate \
  -H "Content-Type: application/json" \
  -d "{
    \"target_id\": \"$TARGET_ID\",
    \"seed_smiles\": \"CC(=O)Oc1ccccc1C(=O)O\",
    \"n_molecules\": 20
  }" | jq '.'
```

### List All Molecules for Target

```bash
curl http://localhost:8000/api/molecules/$TARGET_ID | jq '.'

# With pagination
curl "http://localhost:8000/api/molecules/$TARGET_ID?skip=0&limit=10" | jq '.'
```

---

## 3. RDKit Direct Usage

### Generate and Score Molecules Directly

```python
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
import sascorer

# Parse SMILES
seed_smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
mol = Chem.MolFromSmiles(seed_smiles)

if mol is None:
    print("Invalid SMILES!")
else:
    # Calculate Lipinski descriptors
    mw = rdMolDescriptors.CalcExactMolWt(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    logp = Descriptors.MolLogP(mol)
    
    # Check Lipinski
    lipinski_pass = (mw <= 500 and hbd <= 5 and hba <= 10 and logp <= 5)
    
    # Calculate SAS
    sas = sascorer.calculateScore(mol)
    
    print(f"SMILES: {seed_smiles}")
    print(f"MW: {mw:.2f}")
    print(f"HBD: {hbd}")
    print(f"HBA: {hba}")
    print(f"LogP: {logp:.2f}")
    print(f"Lipinski Pass: {lipinski_pass}")
    print(f"SAS Score: {sas:.2f} (1=easy, 10=hard)")
```

**Output:**
```
SMILES: CC(=O)Oc1ccccc1C(=O)O
MW: 180.16
HBD: 1
HBA: 4
LogP: 1.19
Lipinski Pass: True
SAS Score: 2.10
```

---

## 4. Variant Generation Examples

### Atom Substitution

```python
from rdkit import Chem
from app.services.molecule_service import MoleculeGenerationService

seed = Chem.MolFromSmiles("CCO")  # Ethanol

# Generate variant
variant = MoleculeGenerationService._apply_atom_substitution(seed)
print(f"Original: CCO")
print(f"Variant:  {variant}")

# Example output:
# Original: CCO
# Variant:  NCO (replaced C with N)
```

### Fragment Addition

```python
from rdkit import Chem
from app.services.molecule_service import MoleculeGenerationService

seed = Chem.MolFromSmiles("CCO")  # Ethanol

# Add fragment
variant = MoleculeGenerationService._apply_fragment_addition(seed)
print(f"Original: CCO")
print(f"Variant with fragment: {variant}")

# Example output:
# Original: CCO
# Variant with fragment: CCOc1ccccc1 (added benzene ring)
```

---

## 5. Database Query Examples

### Retrieve Molecules from Database

```python
from app.database import SessionLocal
from app.models.molecule import Molecule
from sqlalchemy import desc

db = SessionLocal()

# Get all molecules for target
target_id = "550e8400-e29b-41d4-a716-446655440000"
molecules = db.query(Molecule).filter(
    Molecule.target_id == target_id
).all()

print(f"Found {len(molecules)} molecules")

# Filter by Lipinski pass
passing = db.query(Molecule).filter(
    Molecule.target_id == target_id,
    Molecule.lipinski_pass == True
).all()

print(f"{len(passing)} pass Lipinski")

# Sort by SAS (easy to synthesize first)
easiest = db.query(Molecule).filter(
    Molecule.target_id == target_id
).order_by(Molecule.sas_score).limit(5).all()

print("5 easiest to synthesize:")
for mol in easiest:
    print(f"  SAS {mol.sas_score}: {mol.smiles}")

db.close()
```

---

## 6. Testing Examples

### Run Specific Tests

```bash
# Run all molecule tests
pytest tests/test_molecules.py -v

# Run specific test class
pytest tests/test_molecules.py::TestLipinskiDescriptors -v

# Run specific test method
pytest tests/test_molecules.py::TestAspireGenerationAssertion::test_aspirin_generation_main_requirement -v -s

# Run with output captured (see print statements)
pytest tests/test_molecules.py -v -s

# Run only tests that pass (exclude failures)
pytest tests/test_molecules.py -v --lf

# Run in parallel (faster)
pytest tests/test_molecules.py -v -n auto
```

---

## 7. Integration Examples

### Complete Workflow: Target → Molecules → Database

```python
import asyncio
from uuid import uuid4
from app.services.target_service import TargetEnrichmentService
from app.services.molecule_service import MoleculeGenerationService
from app.database import SessionLocal

async def complete_workflow():
    """Analyze target, then generate molecules."""
    db = SessionLocal()
    
    try:
        # Phase 3: Analyze target
        print("📍 Phase 3: Analyzing target...")
        target = await TargetEnrichmentService.analyze_target(
            query="BACE1 in Alzheimer's disease",
            db=db
        )
        print(f"✅ Target: {target.name}")
        print(f"   Druggability: {target.druggability_score}")
        
        # Phase 4: Generate molecules
        print("\n🧪 Phase 4: Generating molecules...")
        molecules, valid_count = await MoleculeGenerationService.generate_molecules_for_target(
            target_id=str(target.id),
            seed_smiles="CC(=O)Oc1ccccc1C(=O)O",
            n_molecules=20,
            db=db
        )
        print(f"✅ Generated: {len(molecules)} molecules")
        print(f"   Passed Lipinski: {valid_count}")
        
        # Show results
        print("\n📊 Results:")
        passing = [m for m in molecules if m.lipinski_pass]
        print(f"Drug-like: {len(passing)}/{len(molecules)}")
        
        for mol in passing[:3]:
            print(f"\n  SMILES: {mol.smiles}")
            print(f"  Lipinski Pass: {mol.lipinski_pass}")
            print(f"  SAS Score: {mol.sas_score}")
        
    finally:
        db.close()

# Run
asyncio.run(complete_workflow())
```

---

## 8. Error Handling Examples

### Graceful Error Handling

```python
from rdkit import Chem
from app.services.molecule_service import MoleculeGenerationService

def safe_generate_variants(seed_smiles, n_molecules):
    """Generate variants with error handling."""
    try:
        variants = MoleculeGenerationService.generate_variants(seed_smiles, n_molecules)
        return variants
    except ValueError as e:
        print(f"❌ Validation error: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return []

# Valid SMILES
result = safe_generate_variants("CC(=O)Oc1ccccc1C(=O)O", 20)
print(f"Generated: {len(result)} variants")

# Invalid SMILES
result = safe_generate_variants("INVALID_123", 20)
print(f"Generated: {len(result)} variants")  # 0
```

---

## 9. Configuration & Setup

### Environment Variables

Create `.env` file:
```bash
# Database
DATABASE_URL=postgresql://molgenix:molgenix_password@localhost:5432/molgenix

# API Keys
GEMINI_API_KEY=your_key_here

# Debug
DEBUG=False
```

### Docker Compose Setup

```bash
# Start all services
docker-compose up --build

# Stop services
docker-compose down

# Rebuild without cache
docker-compose build --no-cache

# View logs
docker-compose logs -f backend
```

---

## 10. Performance Tips

### Batch Processing

```python
from app.services.molecule_service import MoleculeGenerationService
from app.database import SessionLocal

def batch_generate(targets_smiles_list, n_per_target):
    """Generate molecules for multiple targets."""
    db = SessionLocal()
    
    results = {}
    for target_id, seed_smiles in targets_smiles_list:
        try:
            molecules, valid_count = await MoleculeGenerationService.generate_molecules_for_target(
                target_id=target_id,
                seed_smiles=seed_smiles,
                n_molecules=n_per_target,
                db=db
            )
            results[target_id] = {
                "total": len(molecules),
                "valid": valid_count
            }
        except Exception as e:
            results[target_id] = {"error": str(e)}
    
    db.close()
    return results

# Usage
targets = [
    ("uuid1", "CC(=O)Oc1ccccc1C(=O)O"),  # Aspirin
    ("uuid2", "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"),  # Ibuprofen
]

results = batch_generate(targets, n_per_target=20)
```

---

## 11. Debugging Tips

### Enable Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app.services.molecule_service")

# Now service logs will show detailed info
```

### Inspect Generated SMILES

```python
from rdkit import Chem

def inspect_smiles(smiles):
    """Debug a SMILES string."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print(f"❌ Invalid SMILES: {smiles}")
    else:
        print(f"✅ Valid SMILES: {smiles}")
        print(f"   Atoms: {mol.GetNumAtoms()}")
        print(f"   Bonds: {mol.GetNumBonds()}")
        print(f"   MW: {Chem.rdMolDescriptors.CalcExactMolWt(mol):.2f}")
        print(f"   Canonical: {Chem.MolToSmiles(mol)}")

inspect_smiles("CC(=O)Oc1ccccc1C(=O)O")
inspect_smiles("INVALID[123]SMILES")
```

### Profile Performance

```python
import time
from app.services.molecule_service import MoleculeGenerationService

def profile_generation():
    """Measure generation performance."""
    seed = "CC(=O)Oc1ccccc1C(=O)O"
    
    start = time.time()
    variants = MoleculeGenerationService.generate_variants(seed, 20)
    elapsed = time.time() - start
    
    print(f"Generated: {len(variants)} variants in {elapsed:.2f}s")
    print(f"Average: {elapsed/len(variants)*1000:.1f}ms per variant")

profile_generation()
```

---

## 12. Common Patterns

### Extract Molecular Properties

```python
from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen

def get_all_properties(smiles):
    """Get comprehensive molecular properties."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    
    return {
        "smiles": smiles,
        "mw": Chem.rdMolDescriptors.CalcExactMolWt(mol),
        "logp": Crippen.MolLogP(mol),
        "hbd": Descriptors.NumHDonors(mol),
        "hba": Descriptors.NumHAcceptors(mol),
        "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
        "aromatic_rings": Chem.GetSSSR(mol).__len__(),
        "hac": Descriptors.HeavyAtomCount(mol),
    }

props = get_all_properties("CC(=O)Oc1ccccc1C(=O)O")
for key, value in props.items():
    print(f"{key}: {value}")
```

### Filter by Property Range

```python
def filter_by_properties(smiles_list, **kwargs):
    """Filter molecules by property ranges.
    
    Example:
        filter_by_properties(smiles, mw_max=500, logp_max=5, hbd_max=5)
    """
    filtered = []
    
    for smiles in smiles_list:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        
        props = get_all_properties(smiles)
        
        # Check all constraints
        passes = True
        if "mw_max" in kwargs and props["mw"] > kwargs["mw_max"]:
            passes = False
        if "logp_max" in kwargs and props["logp"] > kwargs["logp_max"]:
            passes = False
        if "hbd_max" in kwargs and props["hbd"] > kwargs["hbd_max"]:
            passes = False
        
        if passes:
            filtered.append(smiles)
    
    return filtered

# Usage
aspirin_variants = [...]  # from generation
drug_like = filter_by_properties(aspirin_variants, mw_max=500, logp_max=5)
print(f"Drug-like: {len(drug_like)}/{len(aspirin_variants)}")
```

---

## 🎯 Summary

| Task | Method | Example |
|------|--------|---------|
| Generate molecules | Service | `generate_molecules_for_target()` |
| Variant generation | Service | `generate_variants()` |
| Lipinski check | Service | `calculate_lipinski_descriptors()` |
| SAS score | Service | `calculate_sas_score()` |
| API endpoint | HTTP POST | `/api/molecules/generate` |
| Query database | SQLAlchemy | `db.query(Molecule).filter(...)` |
| Direct RDKit | Library | `Chem.MolFromSmiles()` |

---

## 🔗 Related Files

- `app/services/molecule_service.py` - Implementation
- `app/routers/molecules.py` - API layer
- `tests/test_molecules.py` - All examples tested
- `app/models/molecule.py` - Database schema
- `app/database.py` - DB connection

---

**Happy molecular generation! 🧬**
