# MolGenix Backend Summary

## Purpose

This file consolidates the most useful information scattered across the backend markdown files.
It is meant to be the first document to read before opening older phase-specific notes.

## Current Backend State

The backend is a FastAPI-based drug discovery pipeline with:

- target analysis and enrichment
- molecule generation from seed SMILES
- ADMET scoring
- docking support with mock fallback when no receptor is available
- lead optimization
- PDF report generation
- Gemini integration with fallback behavior when no real API key is configured
- PostgreSQL persistence via SQLAlchemy and Alembic
- Docker-based local development

## Main Runtime Flow

The current end-to-end pipeline is:

1. Analyze a target query.
2. Generate candidate molecules from a seed SMILES.
3. Score ADMET properties for generated molecules.
4. Dock the top candidates against a receptor structure.
5. Optimize the best lead.
6. Generate a PDF report.

Main API groups:

- `/api/targets`
- `/api/molecules`
- `/api/admet`
- `/api/docking`
- `/api/optimize`
- `/api/reports`
- `/api/pipeline`

## Core Backend Components

### Database

The database layer uses:

- SQLAlchemy ORM
- PostgreSQL
- Alembic migrations

Main entities:

- `targets`
- `molecules`
- `reports`

Key stored molecule fields include:

- `smiles`
- `lipinski_pass`
- `sas_score`
- `admet_scores`
- `docking_score`
- `is_optimized`

For database details, keep using [DATABASE.md](/c:/Users/Dell/nmit/molgenix/backend/DATABASE.md).

### Target Intelligence

The target analysis layer:

- extracts protein/gene/disease information from a natural-language query
- queries UniProt, ChEMBL, and PDB-related sources
- computes a druggability score
- persists the result
- falls back to query parsing if Gemini extraction is unavailable or empty

### Molecule Generation

The molecule generation layer:

- takes a target and seed SMILES
- generates structural variants with RDKit
- validates molecules
- computes Lipinski and SAS-style scores
- stores viable candidates

### ADMET

The ADMET layer currently supports:

- BBBP scoring
- hepatotoxicity scoring
- hERG risk
- oral bioavailability scoring
- traffic-light classification

It is designed to use richer ML-backed behavior where available, but also contains fallback heuristics so the backend remains operational in constrained environments.

### Docking

Docking expects:

- a receptor `.pdb` file in `backend/data/pdb_files/`
- Vina/Open Babel tooling when real docking is used

If receptor files or docking tools are unavailable, the pipeline can fall back to mock docking scores so the rest of the workflow continues.

### Optimization

Lead optimization:

- creates R-group variants
- rescoring includes Lipinski, SAS, and ADMET-derived signals
- persists the best optimized molecule

### Reports

The reporting service:

- generates PDF reports
- summarizes target and molecule results
- embeds molecule information and scores
- stores report records in the database

## Current Practical Limitations

The backend is runnable, but scientific fidelity depends on environment and assets.

Current limitations to keep in mind:

- Gemini outputs are generic if a real API key is not configured.
- Docking is only fully real when a valid receptor `.pdb` file is present and docking tools are available.
- Some scoring paths may fall back to heuristics if optional ML or chemistry extras are missing.
- Older docs may say a phase is "complete" even when later runtime fixes changed the real state of the system.

## Which Markdown Files Still Matter

These are still useful as focused references:

- [DATABASE.md](/c:/Users/Dell/nmit/molgenix/backend/DATABASE.md): schema and persistence reference
- [ARCHITECTURE-OVERVIEW.md](/c:/Users/Dell/nmit/molgenix/backend/ARCHITECTURE-OVERVIEW.md): high-level system design
- [MOLECULE-GENERATION-EXPLAINED.md](/c:/Users/Dell/nmit/molgenix/backend/MOLECULE-GENERATION-EXPLAINED.md): conceptual explanation of the generation module
- [TARGET-INTELLIGENCE-EXPLANATION.md](/c:/Users/Dell/nmit/molgenix/backend/TARGET-INTELLIGENCE-EXPLANATION.md): conceptual explanation of target enrichment

## Which Markdown Files Are Mostly Redundant

These mostly repeat milestone/status information and are now good archive material:

- [WHAT-WE-BUILT.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/WHAT-WE-BUILT.md)
- [PHASE2-DATABASE-COMPLETE.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/PHASE2-DATABASE-COMPLETE.md)
- [VISUAL-GUIDE-PHASE2.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/VISUAL-GUIDE-PHASE2.md)
- [PHASE3-TARGET-INTELLIGENCE-COMPLETE.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/PHASE3-TARGET-INTELLIGENCE-COMPLETE.md)
- [PHASE4-FINAL-STATUS.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/PHASE4-FINAL-STATUS.md)
- [PHASE4-INTEGRATION-GUIDE.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/PHASE4-INTEGRATION-GUIDE.md)
- [PHASE4-MOLECULE-GENERATION-COMPLETE.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/PHASE4-MOLECULE-GENERATION-COMPLETE.md)
- [PHASE4-QUICK-START.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/PHASE4-QUICK-START.md)
- [VISUAL-SUMMARY-PHASE4.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/VISUAL-SUMMARY-PHASE4.md)
- [CODE-EXAMPLES.md](/c:/Users/Dell/nmit/molgenix/backend/archive-docs/CODE-EXAMPLES.md)

## Recommended Doc Strategy

Use this file as the entry point.

Then keep:

- one summary file
- one database reference
- one architecture reference
- one conceptual file per major module only if it adds real explanatory value

Everything archived has been moved into `backend/archive-docs/` instead of being deleted.
