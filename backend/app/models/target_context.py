from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TargetContext:
    # Core identifiers - set once, never change
    target_id: str
    gene_symbol: str
    protein_name: str
    disease: str

    # External database IDs - set once from target analysis
    uniprot_id: str
    chembl_id: str
    pdb_id: str

    # Biological data
    function: str
    known_inhibitors: int
    druggability_score: float

    # Molecule generation parameters - derived from target biology
    mw_min: float = 200.0
    mw_max: float = 500.0
    preferred_hbd_max: int = 5
    preferred_hba_max: int = 10
    target_class: str = "unknown"

    # Docking parameters
    receptor_pdb_path: Optional[str] = None
    docking_center: Optional[tuple] = None
    docking_box_size: Optional[tuple] = None
