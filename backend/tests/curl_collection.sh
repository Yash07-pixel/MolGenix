#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TARGET_QUERY="${TARGET_QUERY:-BACE1 in Alzheimer's}"
SEED_SMILES="${SEED_SMILES:-CC(=O)Oc1ccccc1C(=O)O}"
PDB_FILENAME="${PDB_FILENAME:-2qmg.pdb}"
TARGET_ID="${TARGET_ID:-00000000-0000-0000-0000-000000000001}"
MOLECULE_ID="${MOLECULE_ID:-00000000-0000-0000-0000-000000000002}"
REPORT_ID="${REPORT_ID:-00000000-0000-0000-0000-000000000003}"

echo "Health"
curl -sS "$BASE_URL/health"

echo
echo "Root"
curl -sS "$BASE_URL/"

echo
echo "Analyze target"
curl -sS -X POST "$BASE_URL/api/targets/analyze" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$TARGET_QUERY\"}"

echo
echo "List targets"
curl -sS "$BASE_URL/api/targets/"

echo
echo "Get target"
curl -sS "$BASE_URL/api/targets/$TARGET_ID"

echo
echo "Generate molecules"
curl -sS -X POST "$BASE_URL/api/molecules/generate" \
  -H "Content-Type: application/json" \
  -d "{\"target_id\":\"$TARGET_ID\",\"seed_smiles\":\"$SEED_SMILES\",\"n_molecules\":10}"

echo
echo "List molecules for target"
curl -sS "$BASE_URL/api/molecules/$TARGET_ID"

echo
echo "Predict ADMET"
curl -sS -X POST "$BASE_URL/api/admet/predict" \
  -H "Content-Type: application/json" \
  -d "{\"molecule_ids\":[\"$MOLECULE_ID\"]}"

echo
echo "Run docking"
curl -sS -X POST "$BASE_URL/api/docking/run" \
  -H "Content-Type: application/json" \
  -d "{\"molecule_id\":\"$MOLECULE_ID\",\"pdb_filename\":\"$PDB_FILENAME\"}"

echo
echo "Docking results"
curl -sS "$BASE_URL/api/docking/results/$TARGET_ID"

echo
echo "Optimize molecule"
curl -sS -X POST "$BASE_URL/api/optimize/molecule" \
  -H "Content-Type: application/json" \
  -d "{\"molecule_id\":\"$MOLECULE_ID\"}"

echo
echo "Generate report"
curl -sS -X POST "$BASE_URL/api/reports/generate" \
  -H "Content-Type: application/json" \
  -d "{\"target_id\":\"$TARGET_ID\"}"

echo
echo "Download report"
curl -sS -o report.pdf "$BASE_URL/api/reports/download/$REPORT_ID"
echo "Saved report.pdf"

echo
echo "Run full pipeline"
curl -sS -X POST "$BASE_URL/api/pipeline/run" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"$TARGET_QUERY\",\"seed_smiles\":\"$SEED_SMILES\",\"n_molecules\":10}"
