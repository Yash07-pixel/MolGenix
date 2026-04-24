"""
Docking Service - AutoDock Vina integration with development fallbacks.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import UUID

from app.config import settings

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Crippen, Descriptors, Lipinski, rdMolDescriptors

    RDKIT_AVAILABLE = True
except ImportError:
    Chem = None
    AllChem = None
    Crippen = None
    Descriptors = None
    Lipinski = None
    rdMolDescriptors = None
    RDKIT_AVAILABLE = False

logger = logging.getLogger(__name__)

VINA_AVAILABLE = shutil.which("vina") is not None
OBABEL_AVAILABLE = shutil.which("obabel") is not None

logger.info("Docking service availability: vina=%s obabel=%s", VINA_AVAILABLE, OBABEL_AVAILABLE)


class DockingService:
    """Run molecular docking or return development-safe heuristic scores."""

    BOX_SIZE = 20.0
    MAX_HEAVY_ATOMS = 40
    MAX_MOLECULAR_WEIGHT = 450.0
    MAX_ROTATABLE_BONDS = 10
    VINA_TIMEOUT_SECONDS = 25
    VINA_SCORE_PATTERN = re.compile(r"^\s*\d+\s+(-?\d+(?:\.\d+)?)\s+", re.MULTILINE)
    FALLBACK_METHOD = "rdkit_fallback"

    @staticmethod
    def _ensure_pdb_path(pdb_filename: str) -> Path:
        pdb_name = Path(pdb_filename).name
        pdb_path = Path(settings.PDB_STORAGE_PATH).resolve() / pdb_name
        base_path = Path(settings.PDB_STORAGE_PATH).resolve()

        if base_path not in pdb_path.parents and pdb_path != base_path:
            raise ValueError("Invalid PDB filename")
        if not pdb_path.exists():
            raise FileNotFoundError(f"PDB file not found: {pdb_name}")
        return pdb_path

    @staticmethod
    def _parse_ligand_centroid_from_pdb(pdb_path: Path) -> Tuple[float, float, float]:
        coords: List[Tuple[float, float, float]] = []

        with pdb_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if not line.startswith("HETATM"):
                    continue
                try:
                    x = float(line[30:38].strip())
                    y = float(line[38:46].strip())
                    z = float(line[46:54].strip())
                except ValueError:
                    continue
                coords.append((x, y, z))

        if not coords:
            logger.warning("No HETATM records found in %s, using origin for docking box", pdb_path.name)
            return 0.0, 0.0, 0.0

        count = float(len(coords))
        return (
            sum(point[0] for point in coords) / count,
            sum(point[1] for point in coords) / count,
            sum(point[2] for point in coords) / count,
        )

    @staticmethod
    def _run_command(command: List[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=DockingService.VINA_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _descriptor_fallback_score(smiles: str) -> float:
        if not RDKIT_AVAILABLE:
            length = max(1, len(smiles))
            base = -4.0 - min(6.0, length / 20.0)
            return round(max(-12.0, min(-2.0, base)), 2)

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid molecule SMILES for docking fallback")

        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)
        _tpsa = rdMolDescriptors.CalcTPSA(mol)
        rot_bonds = Lipinski.NumRotatableBonds(mol)
        aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)

        base = -4.0
        base -= aromatic_rings * 0.8
        base -= hba * 0.3
        base -= hbd * 0.2
        base += (mw / 500.0) * 1.5
        base += (logp - 2.5) * 0.4
        base += rot_bonds * 0.1
        score = max(-12.0, min(-2.0, base))
        return round(score, 2)

    @staticmethod
    def _fallback_result(smiles: str, fallback_reason: str) -> Dict[str, Any]:
        return {
            "docking_score": DockingService._descriptor_fallback_score(smiles),
            "method": DockingService.FALLBACK_METHOD,
            "is_mock": True,
            "fallback_reason": fallback_reason,
        }

    @staticmethod
    def _get_molecule_screening_metrics(smiles: str) -> tuple[float, int, int]:
        if not RDKIT_AVAILABLE:
            return 0.0, 0, 0

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid molecule SMILES")
        return (
            float(Descriptors.MolWt(mol)),
            int(mol.GetNumHeavyAtoms()),
            int(Descriptors.NumRotatableBonds(mol)),
        )

    @staticmethod
    def _write_ligand_sdf(smiles: str, output_path: Path) -> None:
        if not RDKIT_AVAILABLE:
            raise RuntimeError("RDKit is required to build a 3D ligand")

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid molecule SMILES")

        mol = Chem.AddHs(mol)
        embed_status = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if embed_status != 0:
            raise RuntimeError("Failed to embed ligand in 3D")

        optimize_status = AllChem.MMFFOptimizeMolecule(mol)
        if optimize_status == -1:
            logger.warning("MMFF optimization did not converge for ligand")

        writer = Chem.SDWriter(str(output_path))
        try:
            writer.write(mol)
        finally:
            writer.close()

    @staticmethod
    def _prepare_ligand_pdbqt(sdf_path: Path, ligand_pdbqt_path: Path) -> None:
        obabel_path = shutil.which("obabel")
        if not obabel_path:
            raise RuntimeError("Open Babel (obabel) is not available on PATH")

        DockingService._run_command([obabel_path, str(sdf_path), "-O", str(ligand_pdbqt_path)])

    @staticmethod
    def _prepare_receptor_pdbqt(pdb_path: Path, receptor_pdbqt_path: Path) -> None:
        prepare_receptor = shutil.which("prepare_receptor4.py")
        if prepare_receptor:
            DockingService._run_command(
                [
                    prepare_receptor,
                    "-r",
                    str(pdb_path),
                    "-o",
                    str(receptor_pdbqt_path),
                ]
            )
            return

        obabel_path = shutil.which("obabel")
        if not obabel_path:
            raise RuntimeError("Neither prepare_receptor4.py nor obabel is available on PATH")

        DockingService._run_command(
            [obabel_path, str(pdb_path), "-O", str(receptor_pdbqt_path), "-xr", "-xc"]
        )

    @staticmethod
    def _run_vina(
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        output_pdbqt: Path,
        log_path: Path,
        center: Tuple[float, float, float],
    ) -> float:
        vina_path = shutil.which("vina")
        if not vina_path:
            raise RuntimeError("AutoDock Vina is not available on PATH")

        command = [
            vina_path,
            "--receptor",
            str(receptor_pdbqt),
            "--ligand",
            str(ligand_pdbqt),
            "--center_x",
            str(center[0]),
            "--center_y",
            str(center[1]),
            "--center_z",
            str(center[2]),
            "--size_x",
            str(DockingService.BOX_SIZE),
            "--size_y",
            str(DockingService.BOX_SIZE),
            "--size_z",
            str(DockingService.BOX_SIZE),
            "--out",
            str(output_pdbqt),
        ]
        result = DockingService._run_command(command)
        log_path.write_text(
            "\n".join(
                part for part in [result.stdout.strip(), result.stderr.strip()] if part
            ),
            encoding="utf-8",
        )
        return DockingService._parse_vina_log(log_path)

    @staticmethod
    def _parse_vina_log(log_path: Path) -> float:
        if not log_path.exists():
            raise RuntimeError("Vina log file was not created")

        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        matches = DockingService.VINA_SCORE_PATTERN.findall(log_text)
        if not matches:
            raise RuntimeError("Unable to parse docking score from Vina log")
        return float(matches[0])

    @staticmethod
    def _mock_score(smiles: str) -> float:
        return DockingService._descriptor_fallback_score(smiles)

    @staticmethod
    def _persist_score(db: Any, molecule: Any, result: Dict[str, Any], pdb_filename: str) -> None:
        molecule.docking_score = result["docking_score"]
        metadata = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}
        metadata["_docking"] = {
            "method": result["method"],
            "is_mock": result["is_mock"],
            "fallback_reason": result["fallback_reason"],
            "pdb_filename": pdb_filename,
        }
        molecule.admet_scores = metadata
        db.commit()
        db.refresh(molecule)

    @staticmethod
    async def run_docking(molecule_id: str, pdb_filename: str, db: Any) -> Dict[str, Any]:
        """Run docking for a single molecule and receptor file."""
        from app.models.molecule import Molecule

        molecule = db.query(Molecule).filter(Molecule.id == molecule_id).first()
        if not molecule:
            raise ValueError("Molecule not found")

        if not VINA_AVAILABLE:
            result = DockingService._fallback_result(molecule.smiles, "vina_not_found")
            DockingService._persist_score(db, molecule, result, "mock")
            return {
                "molecule_id": str(molecule.id),
                **result,
                "pdb_filename": "mock",
            }

        if not OBABEL_AVAILABLE:
            result = DockingService._fallback_result(molecule.smiles, "obabel_not_found")
            DockingService._persist_score(db, molecule, result, "mock")
            return {
                "molecule_id": str(molecule.id),
                **result,
                "pdb_filename": "mock",
            }

        try:
            pdb_path = DockingService._ensure_pdb_path(pdb_filename)
        except FileNotFoundError:
            result = DockingService._fallback_result(molecule.smiles, "pdb_missing")
            DockingService._persist_score(db, molecule, result, "mock")
            return {
                "molecule_id": str(molecule.id),
                **result,
                "pdb_filename": "mock",
            }

        try:
            molecular_weight, heavy_atom_count, rotatable_bonds = DockingService._get_molecule_screening_metrics(molecule.smiles)
        except ValueError:
            result = DockingService._fallback_result(molecule.smiles, "invalid_smiles")
            DockingService._persist_score(db, molecule, result, "mock")
            return {
                "molecule_id": str(molecule.id),
                **result,
                "pdb_filename": "mock",
            }

        if (
            heavy_atom_count > DockingService.MAX_HEAVY_ATOMS
            or molecular_weight > DockingService.MAX_MOLECULAR_WEIGHT
            or rotatable_bonds > DockingService.MAX_ROTATABLE_BONDS
        ):
            logger.info(
                "Skipping Vina for %s: MW=%.1f, HA=%s, RotB=%s - using fallback score",
                molecule_id,
                molecular_weight,
                heavy_atom_count,
                rotatable_bonds,
            )
            result = DockingService._fallback_result(molecule.smiles, "pre_docking_filter")
            DockingService._persist_score(db, molecule, result, "mock")
            return {
                "molecule_id": str(molecule.id),
                **result,
                "pdb_filename": "mock",
            }

        try:
            with tempfile.TemporaryDirectory(prefix="molgenix_docking_") as temp_dir:
                temp_path = Path(temp_dir)
                ligand_sdf = temp_path / "ligand.sdf"
                ligand_pdbqt = temp_path / "ligand.pdbqt"
                receptor_pdbqt = temp_path / "receptor.pdbqt"
                output_pdbqt = temp_path / "output.pdbqt"
                log_path = temp_path / "vina_log.txt"

                DockingService._write_ligand_sdf(molecule.smiles, ligand_sdf)
                DockingService._prepare_ligand_pdbqt(ligand_sdf, ligand_pdbqt)
                DockingService._prepare_receptor_pdbqt(pdb_path, receptor_pdbqt)
                center = DockingService._parse_ligand_centroid_from_pdb(pdb_path)
                docking_score = DockingService._run_vina(
                    receptor_pdbqt=receptor_pdbqt,
                    ligand_pdbqt=ligand_pdbqt,
                    output_pdbqt=output_pdbqt,
                    log_path=log_path,
                    center=center,
                )
            result = {
                "docking_score": docking_score,
                "method": "vina",
                "is_mock": False,
                "fallback_reason": None,
            }
        except Exception as exc:
            logger.warning("Docking tools unavailable or failed for %s: %s", molecule_id, exc)
            reason = "vina_failed"
            if isinstance(exc, RuntimeError) and "Unable to parse docking score from Vina log" in str(exc):
                reason = "vina_no_score"
            result = DockingService._fallback_result(molecule.smiles, reason)

        DockingService._persist_score(
            db,
            molecule,
            result,
            Path(pdb_filename).name if not result["is_mock"] else "mock",
        )
        return {
            "molecule_id": str(molecule.id),
            **result,
            "pdb_filename": "mock" if result["is_mock"] else Path(pdb_filename).name,
        }

    @staticmethod
    def get_docking_results_for_target(target_id: str, db: Any) -> List[Dict[str, Any]]:
        """Return all docked molecules for a target ordered by best score first."""
        from app.models.molecule import Molecule

        try:
            target_uuid = UUID(str(target_id))
        except ValueError as exc:
            raise ValueError("Invalid target_id") from exc

        molecules = (
            db.query(Molecule)
            .filter(Molecule.target_id == target_uuid, Molecule.docking_score.isnot(None))
            .order_by(Molecule.docking_score.asc())
            .all()
        )

        return [
            {
                "molecule_id": str(molecule.id),
                "target_id": str(molecule.target_id),
                "smiles": molecule.smiles,
                "docking_score": molecule.docking_score,
            }
            for molecule in molecules
        ]
