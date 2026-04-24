# 🧪 Module 2: Molecule Generation Service (RDKit)

## What Problem Does This Solve?

**Input:** A protein/drug target (e.g., BACE1)
**Current State:** We have a target with druggability score, but NO candidate molecules
**Goal:** Generate novel drug-like molecules that might bind to this target

**Example:**
```
User: "I want 20 molecules for BACE1"
System: 
  1. Load aspirin SMILES as seed
  2. Generate 20 variants
  3. Validate each with Lipinski rules
  4. Return viable candidates for further testing
```

---

## 🔬 How Molecule Generation Works

### Step 1: Understanding SMILES
SMILES = Simplified Molecular Input Line Entry System
- Text representation of molecular structure
- Example: `CC(=O)Oc1ccccc1C(=O)O` = Aspirin
  ```
  CC(=O)O      ← Acetyl group
       |
      c1ccccc1  ← Benzene ring
           |
       C(=O)O   ← Carboxylic acid
  ```

### Step 2: Generate Variants (3 Strategies)

#### Strategy A: Random Atom Substitution
Replace atoms at random positions with different functional groups:
```
Original: CC(=O)Oc1ccccc1C(=O)O
                ↓ Replace O with N
Result:   CC(=N)Oc1ccccc1C(=O)O (imide instead of ester)

Original: CC(=O)Oc1ccccc1C(=O)O
                ↓ Replace CH3 with CF3
Result:   CF3C(=O)Oc1ccccc1C(=O)O (fluorinated variant)
```

**Simple substitutions:**
- CH3 → CF3 (add hydrocarbon bulk)
- OH → NH2 (change H-bond donor)
- C → N (change electronics)

#### Strategy B: Fragment Addition
Add small drug-like fragments to the seed:
```
Common Fragments:
['c1ccccc1',        # benzene ring
 'C(=O)N',         # amide group
 'S(=O)(=O)N',     # sulfonamide
 'C(F)(F)F',       # trifluoromethyl
 'OC',             # hydroxyl
 'NC(=O)']         # urea

Example: Aspirin + benzene ring substitution
Original: CC(=O)Oc1ccccc1C(=O)O
                      ↓
Result:   CC(=O)Oc1ccccc(c2ccccc2)c1C(=O)O
                  (added phenyl group to position 4)
```

#### Strategy C: Combination (Substitution + Addition)
```
Random selection:
1. Pick a random position in molecule
2. Pick a random substitution or fragment
3. Apply change
4. Validate
```

### Step 3: Validate Each Generated Molecule

#### Lipinski Rule of Five
Drug-likeness criteria:
```
✅ Pass Rules (Drug-like):
   Molecular Weight      ≤ 500 Da
   H-Bond Donors         ≤ 5
   H-Bond Acceptors      ≤ 10
   LogP (Lipophilicity)  ≤ 5

❌ Fail Rules = Likely too toxic or poorly absorbed
```

**Why These Rules?**
- Heavy molecules can't cross membranes (MW > 500)
- Too many H-bonds = poor bioavailability
- High LogP = accumulation in fat tissue (toxicity)

**Example (Aspirin):**
```
Aspirin: CC(=O)Oc1ccccc1C(=O)O
MW = 180.16      ✅ (< 500)
HBD = 1          ✅ (≤ 5)
HBA = 4          ✅ (≤ 10)
LogP = 1.19      ✅ (≤ 5)
Result: PASSES Lipinski ✅
```

#### SAS (Synthetic Accessibility) Score
How easy is it to synthesize?
```
Range: 1 (easy) to 10 (very hard)

Score ≤ 3: Easy to make in lab (synthetic accessibility good)
Score 3-5: Medium difficulty
Score > 5: Difficult/expensive to synthesize

Uses: 1M commercial molecules + fragment scoring
```

**Example:**
```
Aspirin SAS = 2.1 (easy to make)
Complex scaffold with 10 chiral centers = SAS 8 (hard)
```

---

## 🗂️ Data Model: Molecule Table

```
molecules (table)
├─ id (UUID)
├─ target_id (UUID, FK to targets)  ← Links to parent target
├─ smiles (VARCHAR)                 ← Chemical structure
├─ lipinski_pass (BOOLEAN)          ← Drug-like?
├─ sas_score (FLOAT, 1-10)          ← Synthesis difficulty
├─ molecular_weight (FLOAT)         ← MW from Lipinski
├─ hbd (INT)                        ← H-Bond Donors
├─ hba (INT)                        ← H-Bond Acceptors
├─ logp (FLOAT)                     ← Lipophilicity
└─ created_at (TIMESTAMP)
```

---

## 📡 API Endpoint 1: POST /api/molecules/generate

### Request
```json
{
  "target_id": "550e8400-e29b-41d4-a716-446655440000",
  "seed_smiles": "CC(=O)Oc1ccccc1C(=O)O",
  "n_molecules": 20
}
```

### Processing Steps

```
1. Load Seed SMILES
   └─ RDKit: mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
      └─ Result: Mol object (in-memory molecule representation)

2. Generate N Variants (loop 20 times)
   ├─ For each iteration:
   │  ├─ Pick random position in molecule
   │  ├─ Choose mutation:
   │  │  ├─ 60% = Random atom substitution
   │  │  ├─ 40% = Fragment addition
   │  ├─ Apply RWMol (Read-Write Molecule object)
   │  ├─ Convert back to Mol
   │  └─ Validate with EmbedMolecule (3D check)
   │
   └─ Results: 20 candidate SMILES strings

3. Filter & Score (for each candidate)
   ├─ SMILES → Mol object
   │   └─ If None → Discard (invalid)
   │
   ├─ Calculate Lipinski:
   │  ├─ MW = rdMolDescriptors.CalcExactMolWt(mol)
   │  ├─ HBD = Descriptors.NumHDonors(mol)
   │  ├─ HBA = Descriptors.NumHAcceptors(mol)
   │  ├─ LogP = Descriptors.MolLogP(mol)
   │  └─ lipinski_pass = (MW ≤ 500) AND (HBD ≤ 5) AND (HBA ≤ 10) AND (LogP ≤ 5)
   │
   ├─ Calculate SAS:
   │  └─ sas_score = sascorer.calculateScore(mol)  # 1.0 to 10.0
   │
   └─ Store in database:
       INSERT INTO molecules (target_id, smiles, lipinski_pass, sas_score, ...)

4. Return Results
   ├─ HTTP 201 (Created)
   └─ JSON: [
        {
          "id": "uuid",
          "target_id": "uuid",
          "smiles": "CCO",
          "lipinski_pass": true,
          "sas_score": 1.5,
          "molecular_weight": 46.0,
          "hbd": 1,
          "hba": 1,
          "logp": -0.31
        },
        ...
      ]
```

### Response
```json
{
  "count": 20,
  "target_id": "550e8400-e29b-41d4-a716-446655440000",
  "molecules": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "target_id": "550e8400-e29b-41d4-a716-446655440000",
      "smiles": "CC(=O)Oc1ccccc1C(=O)O",
      "lipinski_pass": true,
      "sas_score": 2.1,
      "molecular_weight": 180.16,
      "hbd": 1,
      "hba": 4,
      "logp": 1.19
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "target_id": "550e8400-e29b-41d4-a716-446655440000",
      "smiles": "CF3C(=O)Oc1ccccc1C(=O)O",
      "lipinski_pass": true,
      "sas_score": 2.3,
      "molecular_weight": 230.16,
      "hbd": 1,
      "hba": 4,
      "logp": 1.65
    },
    ... (18 more)
  ]
}
```

---

## 📡 API Endpoint 2: GET /api/molecules/{target_id}

### Request
```
GET /api/molecules/550e8400-e29b-41d4-a716-446655440000?skip=0&limit=100
```

### Response (200 OK)
```json
{
  "count": 20,
  "target_id": "550e8400-e29b-41d4-a716-446655440000",
  "molecules": [
    {
      "id": "...",
      "smiles": "...",
      "lipinski_pass": true,
      "sas_score": 2.1
    },
    ... (19 more)
  ]
}
```

---

## 🔧 Code Architecture

### app/services/molecule_service.py

```python
class MoleculeGenerationService:
    """Generate drug-like molecules from seed SMILES"""
    
    @staticmethod
    def generate_variants(seed_smiles: str, n_molecules: int) -> List[str]:
        """Generate N SMILES variants from seed"""
        # 1. Load seed SMILES
        # 2. For each iteration:
        #    - Pick random mutation
        #    - Apply and validate
        # 3. Return list of novel SMILES
    
    @staticmethod
    def calculate_lipinski_descriptors(mol) -> Dict:
        """Calculate MW, HBD, HBA, LogP"""
        # Returns: {
        #   "molecular_weight": float,
        #   "hbd": int,
        #   "hba": int,
        #   "logp": float,
        #   "lipinski_pass": bool
        # }
    
    @staticmethod
    def calculate_sas_score(mol) -> float:
        """Calculate Synthetic Accessibility Score"""
        # Uses sascorer library
        # Returns: 1.0 (easy) to 10.0 (hard)
    
    @staticmethod
    async def generate_molecules_for_target(
        target_id: str,
        seed_smiles: str,
        n_molecules: int,
        db: Session
    ) -> List[Molecule]:
        """Orchestrate generation, scoring, and storage"""
        # 1. Generate N variants
        # 2. For each:
        #    - Validate SMILES
        #    - Calculate Lipinski
        #    - Calculate SAS
        # 3. Save to database
        # 4. Return Molecule objects
```

### app/routers/molecules.py

```python
# POST /api/molecules/generate
@router.post("/generate", response_model=List[MoleculeResponse], status_code=201)
async def generate_molecules(
    request: GenerateMoleculesRequest,
    db: Session = Depends(get_db)
):
    """Generate molecules for a target"""
    # 1. Validate target exists
    # 2. Call service.generate_molecules_for_target()
    # 3. Return list of molecules

# GET /api/molecules/{target_id}
@router.get("/{target_id}", response_model=List[MoleculeResponse])
async def get_molecules_for_target(
    target_id: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all molecules for a target"""
    # 1. Query database
    # 2. Return paginated results
```

---

## 📊 Example Execution

### Input
```
POST /api/molecules/generate
{
  "target_id": "550e8400-...",
  "seed_smiles": "CC(=O)Oc1ccccc1C(=O)O",  // Aspirin
  "n_molecules": 20
}
```

### Generation Process
```
Iteration 1: Aspirin + atom substitution → "CF3C(=O)Oc1ccccc1C(=O)O"
Iteration 2: Aspirin + fragment → "CC(=O)Oc1ccccc(S(=O)(=O)N)c1C(=O)O"
Iteration 3: Aspirin + substitution → "CC(=O)Oc1ccccc1C(=N)O"
...
Iteration 20: Aspirin + addition → "CC(=O)Oc1ccccc(c2ccccc2)c1C(=O)O"
```

### Validation
```
Generated SMILES: CF3C(=O)Oc1ccccc1C(=O)O
├─ Valid Mol object? ✅ Yes
├─ MW = 230.16       ✅ (< 500)
├─ HBD = 1           ✅ (≤ 5)
├─ HBA = 4           ✅ (≤ 10)
├─ LogP = 1.65       ✅ (≤ 5)
├─ Lipinski Pass? ✅ YES
├─ SAS Score = 2.3   ✅ (easy to synthesize)
└─ SAVED to database ✅
```

### Output
```json
{
  "count": 20,
  "molecules": [
    {
      "id": "uuid",
      "smiles": "CF3C(=O)Oc1ccccc1C(=O)O",
      "lipinski_pass": true,
      "sas_score": 2.3,
      "molecular_weight": 230.16
    },
    ... (19 more)
  ]
}
```

### Validation Check
```
Generated: 20 molecules
Passed Lipinski: 17 molecules (85%)
Failed Lipinski: 3 molecules (15%)
```

---

## 🚀 Integration with MolGenix Pipeline

```
Phase 3: Target Intelligence ✅
  └─ User specifies target: "BACE1"
     
Phase 4: Molecule Generation (THIS MODULE)
  └─ System generates 20+ variants
     └─ Filter by Lipinski (drug-like)
        
Phase 5: ADMET Prediction
  └─ Predict toxicity for promising molecules
     
Phase 6: Molecular Docking
  └─ Calculate binding affinity vs. BACE1
     
Phase 7: PDF Report
  └─ Top-3 candidates with structures + scores
```

---

## 🧪 Test Strategy

```
Test 1: Generate Molecules from Aspirin
├─ Input: seed_smiles="CC(=O)Oc1ccccc1C(=O)O", n=20
├─ Expect: 20 molecules generated
└─ Assert: At least 10 pass Lipinski

Test 2: Lipinski Validation
├─ Test SMILES with MW > 500 → lipinski_pass = False
├─ Test SMILES with HBD = 10 → lipinski_pass = True
└─ Test SMILES with LogP = 6 → lipinski_pass = False

Test 3: SAS Score Range
├─ Test each molecule: 1.0 ≤ sas_score ≤ 10.0
└─ Assert: All scores within valid range

Test 4: Database Persistence
├─ Generate 5 molecules
├─ Query database
└─ Assert: All 5 found with correct lipinski_pass values

Test 5: API Endpoint
├─ POST /api/molecules/generate
├─ Assert: 201 status code
└─ Assert: Response contains "molecules" array
```

---

## 🎯 Key Implementation Details

### RDKit Operations

```python
# Load SMILES
from rdkit import Chem
mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")

# Generate variant (add atom)
from rdkit.Chem import AllChem
rwmol = Chem.RWMol(mol)
rwmol.AddBond(0, 1, Chem.BondType.SINGLE)  # Add bond
mol_variant = rwmol.GetMol()

# Validate
if AllChem.EmbedMolecule(mol_variant) >= 0:
    smiles_variant = Chem.MolToSmiles(mol_variant)

# Descriptors
from rdkit.Chem import Descriptors, rdMolDescriptors
mw = rdMolDescriptors.CalcExactMolWt(mol)
logp = Descriptors.MolLogP(mol)
```

### SAS Scoring

```python
import sascorer

# Initialize (pre-computed fragment scores)
score = sascorer.calculateScore(mol)
# Returns: float between 1.0 (easy) and 10.0 (hard)
```

### Database Integration

```python
molecule = Molecule(
    target_id=target_id,
    smiles=smiles,
    lipinski_pass=lipinski_pass,
    sas_score=sas_score,
    molecular_weight=mw,
    hbd=hbd,
    hba=hba,
    logp=logp
)
db.add(molecule)
db.commit()
```

---

## ⚠️ Error Handling

```
Invalid seed SMILES
→ Chem.MolFromSmiles() returns None
→ Raise HTTPException(400, "Invalid seed SMILES")

Generation fails (all variants invalid)
→ Return empty list
→ HTTP 200 with {"molecules": []}

Database insert fails
→ db.commit() raises SQLAlchemyError
→ Raise HTTPException(500, "Database error")

Unknown target_id
→ Query returns None
→ Raise HTTPException(404, "Target not found")
```

---

## ✅ Success Criteria

- ✅ Generate 20 molecules from aspirin SMILES
- ✅ At least 10 pass Lipinski Rule of Five
- ✅ SAS scores calculated for all
- ✅ All saved to `molecules` table
- ✅ Endpoints return proper HTTP codes
- ✅ Comprehensive tests pass

