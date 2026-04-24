# 🧬 Module 1: Target Intelligence Engine — Complete Explanation

## 🎯 What We're Building

This is **Module 1** of MolGenix — the system that takes a researcher's natural language question about a disease and returns a **fully enriched protein target** with all the data needed for drug discovery.

---

## 📊 The Problem We're Solving

### Scenario: A Researcher Types
```
"BACE1 protease in Alzheimer's disease"
```

### What They Need to Know
```
❓ What is BACE1 exactly?
❓ What gene encodes it?
❓ What does it do in cells?
❓ Where is it located?
❓ Do we have drugs against it?
❓ Are there any PDB structures?
❓ How "druggable" is it?
```

### Without Module 1
```
😞 They have to manually:
1. Search UniProt → Get protein info
2. Go to PubMed → Find disease context
3. Check ChEMBL → Look for known drugs
4. Find PDB → Get 3D structure
5. Calculate scoring → Determine druggability
(All manual, error-prone, time-consuming)
```

### With Module 1 (What We're Building)
```
✅ One API call:
POST /api/targets/analyze
{ "query": "BACE1 protease in Alzheimer's disease" }

✅ Immediate response:
{
  "name": "Beta-secretase 1",
  "gene_symbol": "BACE1",
  "uniprot_id": "P56817",
  "disease_context": "Alzheimer's disease",
  "organism": "Homo sapiens",
  "function": "Aspartic protease cleaves amyloid precursor protein",
  "subcellular_location": "Golgi apparatus, endoplasmic reticulum",
  "chembl_id": "CHEMBL2095199",
  "target_type": "PROTEIN COMPLEX",
  "known_inhibitors": 847,
  "has_pdb_structure": true,
  "druggability_score": 1.0,
  "created_at": "2026-04-18T12:34:56Z"
}

✅ Then they can generate molecules against it → predict ADMET → dock

```

---

## 🔌 External APIs We're Using

### 1. **Gemini API (Google AI)**
**What it does:** Natural Language Processing  
**Why we use it:** Extract structured data from unstructured text

```
Input: "BACE1 protease in Alzheimer's disease"
         ↓ Gemini AI extracts ↓
Output: {
  "protein_name": "Beta-secretase 1",
  "gene_symbol": "BACE1",
  "disease": "Alzheimer's disease"
}
```

**URL:** Virtual API (no HTTP endpoint, uses Google SDK)  
**Authentication:** Requires `GEMINI_API_KEY` in `.env`  
**Cost:** Free tier available  
**Latency:** ~1-2 seconds

---

### 2. **UniProt REST API**
**What it does:** Protein sequence database with comprehensive metadata  
**Why we use it:** Get official protein info (organism, function, location)

```
URL: https://rest.uniprot.org/uniprotkb/search?query=BACE1&format=json

Returns:
{
  "results": [{
    "uniProtkbId": "BACE1_HUMAN",
    "organism": {
      "scientificName": "Homo sapiens"
    },
    "comments": [{
      "commentType": "FUNCTION",
      "texts": [{
        "value": "Aspartic protease cleaves amyloid precursor protein..."
      }]
    }],
    "features": [{
      "type": "SUBCELLULAR_LOCATION",
      "description": "Golgi apparatus, endoplasmic reticulum"
    }]
  }]
}
```

**URL:** https://rest.uniprot.org/uniprotkb/search  
**Authentication:** None required (public)  
**Cost:** Free  
**Rate limit:** 1 request/second  

---

### 3. **ChEMBL API** (EBI — European Bioinformatics Institute)
**What it does:** Drug target database with known inhibitors  
**Why we use it:** Find how many drugs/compounds target this protein

```
URL: https://www.ebi.ac.uk/chembl/api/data/target/search?q=BACE1&format=json

Returns:
{
  "targets": [{
    "chembl_id": "CHEMBL2095199",
    "target_type": "PROTEIN COMPLEX",
    "organism": "Homo sapiens",
    "activities_count": 847,  ← Heavy drug development!
    "active_compound_count": 412
  }]
}
```

**URL:** https://www.ebi.ac.uk/chembl/api/data/target/search  
**Authentication:** None required (public)  
**Cost:** Free  
**Rate limit:** No strict limit (be respectful)  

---

### 4. **PDB (Protein Data Bank) via RCSB**
**What it does:** 3D protein structures resolved by X-ray crystallography/cryo-EM  
**Why we use it:** Check if 3D structure exists (needed for docking)

```
URL: https://www.rcsb.org/search/select?q=BACE1&rows=1&return_type=json

Returns:
{
  "response": {
    "numFound": 1247,  ← Thousands of BACE1 structures!
    "docs": [{
      "struct_id": "1FKN",
      "title": "COMPLEX OF HUMAN BETA-SECRETASE 1 (BACE) WITH AN INHIBITOR"
    }]
  }
}
```

**URL:** https://www.rcsb.org/search/select  
**Authentication:** None required (public)  
**Cost:** Free  
**Rate limit:** None (public research database)  

---

## 🔄 Step-by-Step Data Flow

```
Researcher Input
    ↓
┌─────────────────────────────────────────────────────────────┐
│  /api/targets/analyze                                       │
│  Input: { "query": "BACE1 protease in Alzheimer's..." }    │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────────┐
│  ① Gemini NLP: Extract protein/gene/disease                │
│     ↓ Gemini API Call ↓                                     │
│     Output: name="Beta-secretase 1", gene="BACE1"          │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────────┐
│  ② UniProt Query: Get full protein metadata                │
│     ↓ HTTP GET to UniProt API ↓                             │
│     Output: organism, function, location                    │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────────┐
│  ③ ChEMBL Query: Get drug target info                      │
│     ↓ HTTP GET to ChEMBL API ↓                              │
│     Output: chembl_id, known_inhibitors=847                │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────────┐
│  ④ PDB Query: Check for 3D structures                       │
│     ↓ HTTP GET to RCSB API ↓                                │
│     Output: has_pdb_structure=true                          │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────────┐
│  ⑤ Calculate Druggability Score                            │
│     - ChEMBL entries: +0.4                                  │
│     - Known inhibitors > 10: +0.3                           │
│     - Human protein: +0.2                                   │
│     - Has PDB structure: +0.1                               │
│     ↓                                                       │
│     Total: 0.4 + 0.3 + 0.2 + 0.1 = 1.0 (Perfect!)         │
└──────────────┬──────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────────┐
│  ⑥ Save to PostgreSQL targets table                        │
│     INSERT INTO targets (name, gene_symbol, ...)           │
│     Returns: id=<UUID>                                      │
└──────────────┬──────────────────────────────────────────────┘
               ↓
Response JSON with all enriched fields
    ↓
Researcher can now generate molecules against BACE1
```

---

## 📊 Druggability Score Algorithm

```python
druggability_score = 0.0

# Rule 1: Has ChEMBL entries (target exists in drug database)
if has_chembl_target:
    druggability_score += 0.4  # Indicates known drug target

# Rule 2: Strong known inhibitor base (many research compounds)
if known_inhibitors > 10:
    druggability_score += 0.3  # Many compounds = easier to drug

# Rule 3: Human protein (not animal model)
if organism == "Homo sapiens":
    druggability_score += 0.2  # Direct human relevance

# Rule 4: 3D structure available (needed for docking)
if has_pdb_structure:
    druggability_score += 0.1  # Can do computational docking

# Final score: 0.0 (impossible) to 1.0 (ideal target)
# Clipped to [0, 1] range
druggability_score = min(druggability_score, 1.0)
```

**Examples:**
```
BACE1 (Alzheimer's):
  ChEMBL: ✅ +0.4
  Inhibitors > 10: ✅ +0.3 (847 known!)
  Human: ✅ +0.2
  PDB structures: ✅ +0.1 (1247 structures!)
  ──────────────────
  Score: 1.0 ⭐⭐⭐⭐⭐ (Perfect!)

Unknown protein:
  ChEMBL: ❌ +0.0
  Inhibitors > 10: ❌ +0.0
  Human: ✅ +0.2
  PDB structures: ❌ +0.0
  ──────────────────
  Score: 0.2 ⚠️ (Difficult to drug)
```

---

## 🔗 API Endpoints We're Building

### Endpoint 1: Analyze Target (POST)
```
POST /api/targets/analyze
Content-Type: application/json

Request:
{
  "query": "BACE1 protease in Alzheimer's disease"
}

Processing:
1. Extract protein info via Gemini
2. Query UniProt, ChEMBL, PDB (parallel)
3. Calculate druggability score
4. Save to database
5. Return enriched data

Response (201 Created):
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Beta-secretase 1",
  "gene_symbol": "BACE1",
  "uniprot_id": "P56817",
  "disease_context": "Alzheimer's disease",
  "organism": "Homo sapiens",
  "function": "Aspartic protease cleaves amyloid precursor protein",
  "subcellular_location": "Golgi apparatus, endoplasmic reticulum",
  "chembl_id": "CHEMBL2095199",
  "target_type": "PROTEIN COMPLEX",
  "known_inhibitors": 847,
  "has_pdb_structure": true,
  "druggability_score": 1.0,
  "created_at": "2026-04-18T12:34:56+00:00"
}
```

### Endpoint 2: Get Target by ID (GET)
```
GET /api/targets/550e8400-e29b-41d4-a716-446655440000

Response (200 OK):
{
  ... same data ...
}
```

### Endpoint 3: List All Targets (GET)
```
GET /api/targets/

Response (200 OK):
{
  "count": 3,
  "targets": [
    { "id": "...", "name": "BACE1", ... },
    { "id": "...", "name": "HER2", ... },
    { "id": "...", "name": "TNFα", ... }
  ]
}
```

---

## 🧪 Testing Strategy

We'll create unit tests for:

1. **Gemini NLP extraction** — Does it parse protein names correctly?
2. **UniProt API query** — Does it fetch protein metadata?
3. **ChEMBL API query** — Does it find drug targets?
4. **PDB API query** — Does it check for structures?
5. **Druggability scoring** — Is the math correct?
6. **Database persistence** — Does data save correctly?
7. **API endpoints** — Do HTTP requests work?
8. **Error handling** — What if APIs are down?

```bash
pytest tests/test_targets.py -v
# Output: 8 tests passed ✅
```

---

## 🎯 What Information Each API Provides

| API | Purpose | Data Retrieved | Rate Limit |
|-----|---------|------------------|-----------|
| **Gemini** | NLP extraction | protein name, gene, disease | Free tier |
| **UniProt** | Protein metadata | function, location, organism | 1/sec |
| **ChEMBL** | Drug targets | known inhibitors, chembl_id | Unlimited |
| **PDB/RCSB** | 3D structures | structure count, PDB IDs | Unlimited |

---

## 💾 Database Schema (Review)

```
targets table:
├─ id (UUID) ← Generated automatically
├─ name (VARCHAR) ← From Gemini
├─ uniprot_id (VARCHAR) ← From UniProt
├─ druggability_score (FLOAT) ← Calculated
├─ created_at (TIMESTAMP) ← Auto-set
└─ (Other fields like gene_symbol, organism, etc.)
```

After saving, the target can be:
- Used to generate molecules
- Linked to docking results
- Associated with reports

---

## ⚡ Performance Optimization

The service makes 4 API calls. To make it fast:

```python
# ❌ Serial (slow): 5 seconds
gemini_result = gemini_api.call()        # 2 sec
uniprot_result = uniprot_api.query()     # 1 sec
chembl_result = chembl_api.query()       # 1 sec
pdb_result = pdb_api.query()             # 1 sec
# Total: 5 seconds

# ✅ Parallel (fast): 2 seconds
results = asyncio.gather(
    gemini_api.call(),                   # 2 sec
    uniprot_api.query(),                 # 1 sec (concurrent)
    chembl_api.query(),                  # 1 sec (concurrent)
    pdb_api.query()                      # 1 sec (concurrent)
)
# Total: 2 seconds (limited by slowest = Gemini at 2 sec)
```

---

## 🎁 What We're Delivering

```
✅ routers/targets.py
   - POST /api/targets/analyze
   - GET /api/targets/{target_id}
   - GET /api/targets/

✅ services/target_service.py
   - analyze_target(query: str) → enriched target
   - get_target(target_id: UUID) → target from DB
   - list_targets() → all targets

✅ ML wrapper for Gemini (app/ml/gemini_extractor.py)
   - extract_target_info(query: str) → parsed JSON

✅ tests/test_targets.py
   - 8+ unit tests with pytest + httpx
   - Mock API calls
   - Test error cases

✅ All async/concurrent for performance
```

---

## 🚀 Next Steps After This Phase

Once Target Intelligence is complete:

1. **Module 2:** Molecule Generator (RDKit + fragment-based generation)
2. **Module 3:** ADMET Predictor (DeepChem toxicity models)
3. **Module 4:** Molecular Docking (AutoDock Vina integration)
4. **Module 5:** PDF Report Generator (ReportLab)

Then the full pipeline works end-to-end:
```
Query → Analyze Target → Generate Molecules → ADMET → Docking → PDF Report
```

---

## 📞 TL;DR

**Target Intelligence Module:**
- Takes natural language (e.g., "BACE1 in Alzheimer's")
- Calls 4 external APIs in parallel
- Enriches with protein metadata
- Calculates druggability score
- Saves to database
- Returns JSON for next module

**External APIs:**
1. Gemini → NLP extraction
2. UniProt → Protein biology
3. ChEMBL → Drug target info
4. PDB/RCSB → 3D structures

**Result:** Researchers can validate targets before spending time on molecule generation!

