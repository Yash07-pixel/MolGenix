"""
Report Service - Generate PDF drug discovery reports with ReportLab.
"""

from __future__ import annotations

import asyncio
import io
import logging
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID, uuid4

from app.services.gemini_service import GeminiService

try:
    from rdkit import Chem
    from rdkit.Chem import Draw

    RDKIT_AVAILABLE = True
except ImportError:
    Chem = None
    Draw = None
    RDKIT_AVAILABLE = False

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)


class ReportService:
    """Generate and persist PDF reports for a target and its molecules."""

    REPORT_STORAGE_DIR = Path("/tmp/reports")

    REQUIRED_ADMET_KEYS = {
        "bbbp_score",
        "hepatotoxicity_score",
        "herg_risk",
        "bioavailability_score",
        "solubility_score",
        "clearance_score",
        "cyp3a4_liability",
        "model_source",
    }

    @staticmethod
    def _styles():
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="MolTitle", fontSize=22, leading=28, spaceAfter=12))
        styles.add(ParagraphStyle(name="MolSubtitle", fontSize=13, leading=17, spaceAfter=8, textColor=colors.HexColor("#334155")))
        styles.add(ParagraphStyle(name="MolHeading", fontSize=17, leading=21, spaceAfter=10, textColor=colors.HexColor("#0f172a")))
        styles.add(ParagraphStyle(name="MolBody", fontSize=10, leading=14, spaceAfter=8, textColor=colors.HexColor("#111827")))
        styles.add(ParagraphStyle(name="MolSmall", fontSize=9, leading=12, spaceAfter=6, textColor=colors.HexColor("#475569")))
        styles.add(ParagraphStyle(name="MolLabel", fontSize=9, leading=11, spaceAfter=4, textColor=colors.HexColor("#64748b")))
        styles.add(ParagraphStyle(name="MolTable", fontSize=8.5, leading=10.5, spaceAfter=0, textColor=colors.HexColor("#111827")))
        return styles

    @staticmethod
    def _traffic_color(value: str) -> colors.Color:
        mapping = {
            "green": colors.HexColor("#1b8a3b"),
            "yellow": colors.HexColor("#c99700"),
            "red": colors.HexColor("#c0392b"),
            "unknown": colors.HexColor("#6b7280"),
        }
        return mapping.get(str(value).lower(), colors.HexColor("#6b7280"))

    @staticmethod
    def _molecule_report_name(index: int, molecule: Any) -> str:
        if getattr(molecule, "is_optimized", False):
            return f"MGX-OPT-{index:02d}"
        return f"MGX-{index:03d}"

    @staticmethod
    def _molecule_descriptors(molecule: Any) -> Dict[str, Any]:
        admet = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}
        return {
            "molecular_weight": admet.get("molecular_weight", "N/A"),
            "logp": admet.get("logp", "N/A"),
            "hbd": admet.get("hbd", "N/A"),
            "hba": admet.get("hba", "N/A"),
        }

    @staticmethod
    def _format_value(value: Any, digits: int = 2) -> str:
        if value in (None, "", "N/A"):
            return "N/A"
        if isinstance(value, (int, float)):
            return f"{value:.{digits}f}"
        return str(value)

    @staticmethod
    def _has_complete_admet(admet_scores: Dict[str, Any]) -> bool:
        if not isinstance(admet_scores, dict):
            return False
        return all(key in admet_scores for key in ReportService.REQUIRED_ADMET_KEYS)

    @staticmethod
    async def _ensure_molecule_annotations(target: Any, molecules: List[Any], db: Any) -> List[Any]:
        """Backfill ADMET and provenance fields for report rendering."""
        from app.models.molecule import Molecule
        from app.services.admet_service import ADMETService

        missing_admet_ids = [
            str(molecule.id)
            for molecule in molecules
            if not ReportService._has_complete_admet(molecule.admet_scores or {})
        ]
        if missing_admet_ids:
            await ADMETService.predict_admet_for_molecules(missing_admet_ids, db)

        refreshed: List[Any] = []
        for molecule in molecules:
            refreshed_molecule = db.query(Molecule).filter(Molecule.id == molecule.id).first() or molecule
            metadata = dict(refreshed_molecule.admet_scores or {})
            docking_meta = metadata.get("_docking")

            if refreshed_molecule.docking_score is not None and not isinstance(docking_meta, dict):
                metadata["_docking"] = {
                    "method": "legacy_stored_score",
                    "is_mock": False,
                    "fallback_reason": None,
                    "pdb_filename": "unknown",
                }
            elif refreshed_molecule.docking_score is None and not isinstance(docking_meta, dict):
                metadata["_docking"] = {
                    "method": "not_run",
                    "is_mock": False,
                    "fallback_reason": "not_run",
                    "pdb_filename": "N/A",
                }

            if metadata != (refreshed_molecule.admet_scores or {}):
                refreshed_molecule.admet_scores = metadata
                db.add(refreshed_molecule)

            refreshed.append(refreshed_molecule)

        if missing_admet_ids or any((molecule.admet_scores or {}).get("_docking") for molecule in refreshed):
            db.commit()
            for molecule in refreshed:
                db.refresh(molecule)

        return refreshed

    @staticmethod
    def _generate_target_summary(target_name: str, target_context: Dict[str, Any]) -> str:
        return GeminiService.generate_target_summary(target_name, target_context)

    @staticmethod
    async def _ensure_target_context(target: Any) -> Any:
        """Hydrate report fields that are not persisted on the Target model."""
        required_fields = (
            "disease",
            "chembl_id",
            "known_inhibitors",
            "structure_count",
            "pdb_id",
            "function",
            "druggability_breakdown",
            "gemini_source",
        )
        if all(getattr(target, field, None) not in (None, "") for field in required_fields):
            return target

        from app.services.target_service import TargetEnrichmentService

        inferred = TargetEnrichmentService.infer_target_info_from_query(getattr(target, "name", "") or "")
        gene_symbol = inferred.get("gene_symbol") or getattr(target, "name", "")

        uniprot_result, chembl_result, pdb_result = await asyncio.gather(
            TargetEnrichmentService.query_uniprot(gene_symbol),
            TargetEnrichmentService.query_chembl(gene_symbol),
            TargetEnrichmentService.query_pdb(gene_symbol),
            return_exceptions=True,
        )

        uniprot_result = uniprot_result if isinstance(uniprot_result, dict) else {}
        chembl_result = chembl_result if isinstance(chembl_result, dict) else {}
        pdb_result = pdb_result if isinstance(pdb_result, dict) else {}

        _, breakdown = TargetEnrichmentService.calculate_druggability_score(
            has_chembl=bool(chembl_result.get("chembl_id")),
            known_inhibitors=chembl_result.get("known_inhibitors", 0),
            organism=uniprot_result.get("organism", ""),
            has_pdb=pdb_result.get("has_pdb_structure", False),
            structure_count=pdb_result.get("structure_count", 0),
            protein_name=getattr(target, "name", "") or "",
            gene_symbol=gene_symbol,
        )

        target.disease = getattr(target, "disease", None) or inferred.get("disease") or "N/A"
        target.chembl_id = getattr(target, "chembl_id", None) or chembl_result.get("chembl_id") or "N/A"
        target.known_inhibitors = (
            getattr(target, "known_inhibitors", None)
            if getattr(target, "known_inhibitors", None) is not None
            else chembl_result.get("known_inhibitors", 0)
        )
        target.structure_count = (
            getattr(target, "structure_count", None)
            if getattr(target, "structure_count", None) is not None
            else pdb_result.get("structure_count", 0)
        )
        target.pdb_id = getattr(target, "pdb_id", None) or pdb_result.get("pdb_id") or "N/A"
        target.function = getattr(target, "function", None) or uniprot_result.get("function") or ""
        target.druggability_breakdown = getattr(target, "druggability_breakdown", None) or breakdown
        target.gemini_source = getattr(target, "gemini_source", None) or "report_hydrated"
        return target

    @staticmethod
    def _molecule_image(smiles: str) -> io.BytesIO | None:
        if not RDKIT_AVAILABLE:
            return None

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        image = Draw.MolToImage(mol, size=(300, 220))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    def _admet_table(admet_scores: Dict[str, Any]) -> Table:
        rows = [
            ["Property", "Value", "Traffic"],
            ["BBBP", ReportService._format_value(admet_scores.get("bbbp_score", "N/A")), admet_scores.get("bbbp_traffic", "unknown")],
            [
                "Hepatotoxicity",
                ReportService._format_value(admet_scores.get("hepatotoxicity_score", "N/A")),
                admet_scores.get("hepatotoxicity_traffic", "unknown"),
            ],
            ["hERG", "risk" if admet_scores.get("herg_risk") else "no risk", "red" if admet_scores.get("herg_risk") else "green"],
            [
                "Bioavailability",
                ReportService._format_value(admet_scores.get("bioavailability_score", "N/A")),
                admet_scores.get("bioavailability_traffic", "unknown"),
            ],
            ["Solubility", ReportService._format_value(admet_scores.get("solubility_score", "N/A")), admet_scores.get("solubility_traffic", "unknown")],
            ["Clearance", ReportService._format_value(admet_scores.get("clearance_score", "N/A")), admet_scores.get("clearance_traffic", "unknown")],
            ["CYP3A4", ReportService._format_value(admet_scores.get("cyp3a4_liability", "N/A")), admet_scores.get("cyp3a4_traffic", "unknown")],
        ]
        table = Table(rows, colWidths=[1.8 * inch, 1.4 * inch, 1.2 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        for row_index in range(1, len(rows)):
            traffic = str(rows[row_index][2]).lower()
            table.setStyle(
                TableStyle(
                    [
                        ("TEXTCOLOR", (2, row_index), (2, row_index), ReportService._traffic_color(traffic)),
                        ("FONTNAME", (2, row_index), (2, row_index), "Helvetica-Bold"),
                    ]
                )
            )
        return table

    @staticmethod
    def _target_summary_table(target: Any) -> Table:
        gene = getattr(target, "gene_symbol", None) or getattr(target, "gene", None) or target.name
        disease = getattr(target, "disease", None) or "N/A"
        known_inhibitors = getattr(target, "known_inhibitors", None)
        chembl_id = getattr(target, "chembl_id", None) or "N/A"

        rows = [
            ["UniProt ID", target.uniprot_id or "N/A"],
            ["Gene", gene or "N/A"],
            ["Disease", disease],
            ["Known Inhibitors", str(known_inhibitors) if known_inhibitors is not None else "N/A"],
            ["ChEMBL ID", chembl_id],
            ["PDB Structures", str(getattr(target, "structure_count", "N/A") or "N/A")],
            ["Top PDB ID", getattr(target, "pdb_id", None) or "N/A"],
        ]
        table = Table(rows, colWidths=[1.8 * inch, 4.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    @staticmethod
    def _overview_metrics_table(target: Any, molecules: List[Any]) -> Table:
        best_docking = next((molecule.docking_score for molecule in molecules if molecule.docking_score is not None), None)
        optimized_count = sum(1 for molecule in molecules if getattr(molecule, "is_optimized", False))
        lipinski_rate = (
            round(sum(1 for molecule in molecules if molecule.lipinski_pass) / len(molecules) * 100)
            if molecules
            else 0
        )
        rows = [
            ["Overview Metric", "Value"],
            ["Generated Compounds Reviewed", str(len(molecules))],
            ["Lipinski Pass Rate", f"{lipinski_rate}%"],
            ["Best Docking Score", f"{best_docking:.2f} kcal/mol" if best_docking is not None else "N/A"],
            ["Optimized Leads", str(optimized_count)],
            ["Druggability Score", f"{round(getattr(target, 'druggability_score', 0.0) or 0.0, 2)}/1.0"],
        ]
        table = Table(rows, colWidths=[2.6 * inch, 2.4 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return table

    @staticmethod
    def _traffic_legend_table() -> Table:
        styles = ReportService._styles()
        cell_style = styles["MolTable"]
        header_style = ParagraphStyle(
            "MolTableHeader",
            parent=cell_style,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#0f172a"),
        )

        def cell(text: str, *, header: bool = False) -> Paragraph:
            safe = html.escape(text)
            return Paragraph(safe, header_style if header else cell_style)

        rows = [
            [cell("Domain", header=True), cell("Green", header=True), cell("Yellow", header=True), cell("Red", header=True)],
            [cell("BBBP / Bioavailability / Solubility / Clearance"), cell("> 0.70"), cell("0.40 to 0.70"), cell("< 0.40")],
            [cell("Hepatotoxicity / CYP3A4 Liability"), cell("< 0.30"), cell("0.30 to 0.60"), cell("> 0.60")],
            [cell("hERG"), cell("No predicted risk"), cell("Borderline; review confidence"), cell("Predicted risk present")],
            [cell("SAS Score"), cell("<= 3.00"), cell("3.01 to 6.00"), cell("> 6.00")],
            [cell("Docking Score"), cell("<= -7.0 kcal/mol"), cell("-7.0 to -5.0 kcal/mol"), cell("> -5.0 kcal/mol")],
        ]
        table = Table(rows, colWidths=[2.8 * inch, 1.1 * inch, 1.25 * inch, 1.1 * inch], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("BACKGROUND", (1, 1), (1, -1), colors.HexColor("#ecfdf5")),
                    ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#fef9c3")),
                    ("BACKGROUND", (3, 1), (3, -1), colors.HexColor("#fee2e2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    @staticmethod
    def _molecule_identity_table(index: int, molecule: Any) -> Table:
        rows = [
            ["Assigned Report Name", ReportService._molecule_report_name(index, molecule)],
            ["Internal Rank", f"Lead Candidate {index}"],
            ["SMILES", molecule.smiles],
            ["Lipinski Status", "Pass" if molecule.lipinski_pass else "Fail"],
            ["SAS Score", ReportService._format_value(molecule.sas_score)],
            ["Docking Score", f"{ReportService._format_value(molecule.docking_score)} kcal/mol" if molecule.docking_score is not None else "N/A"],
        ]
        table = Table(rows, colWidths=[2.0 * inch, 4.3 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    @staticmethod
    def _target_label(target: Any) -> str:
        disease = getattr(target, "disease", None)
        return f"{target.name} in {disease}" if disease and disease != "N/A" else str(getattr(target, "name", "this target"))

    @staticmethod
    def _admet_interpretation_snippets(admet: Dict[str, Any]) -> List[str]:
        snippets: List[str] = []

        if admet.get("hepatotoxicity_traffic") == "red":
            snippets.append("hepatotoxicity is the main development liability")
        elif admet.get("hepatotoxicity_traffic") == "green":
            snippets.append("hepatotoxicity risk appears comparatively manageable")

        if admet.get("herg_risk") is True:
            snippets.append("predicted hERG liability would need explicit follow-up")
        elif admet.get("herg_risk") is False:
            snippets.append("no major hERG warning is currently predicted")

        if admet.get("bioavailability_traffic") == "green":
            snippets.append("oral exposure potential is directionally supportive")
        elif admet.get("bioavailability_traffic") == "red":
            snippets.append("bioavailability may limit progression without chemistry refinement")

        if admet.get("cyp3a4_traffic") == "red":
            snippets.append("CYP3A4 liability suggests possible metabolism or interaction concerns")

        if admet.get("solubility_traffic") == "red":
            snippets.append("solubility could become a formulation and assay constraint")

        if not snippets:
            snippets.append("the ADMET profile is mixed and should be interpreted as an early triage signal rather than a decision-ready profile")

        return snippets[:3]

    @staticmethod
    def _compound_interpretation(target: Any, molecule: Any, index: int) -> str:
        admet = molecule.admet_scores or {}
        descriptors = ReportService._molecule_descriptors(molecule)
        name = ReportService._molecule_report_name(index, molecule)
        target_label = ReportService._target_label(target)
        admet_summary = "; ".join(ReportService._admet_interpretation_snippets(admet))
        docking_note = (
            f"The docking score for {name} is {molecule.docking_score:.2f} kcal/mol, which is interpreted as "
            + ("strong" if molecule.docking_score is not None and molecule.docking_score <= -7 else "moderate" if molecule.docking_score is not None and molecule.docking_score <= -5 else "weak or uncertain")
            + f" predicted receptor engagement for {target_label} under the current workflow."
            if molecule.docking_score is not None
            else f"No docking score was available for {name}; binding interpretation against {target_label} should therefore remain provisional."
        )
        return (
            f"{name} is presented as Lead Candidate {index} for {target_label}. The compound shows a synthetic accessibility "
            f"score of {ReportService._format_value(molecule.sas_score)}, indicating "
            f"{'relatively straightforward' if molecule.sas_score is not None and molecule.sas_score <= 3 else 'moderate' if molecule.sas_score is not None and molecule.sas_score <= 6 else 'challenging'} "
            f"expected tractability for synthesis. The recorded molecular weight is {ReportService._format_value(descriptors['molecular_weight'])} Da and the LogP estimate is "
            f"{ReportService._format_value(descriptors['logp'])}, which should be interpreted together with Lipinski status "
            f"({'pass' if molecule.lipinski_pass else 'fail'}) when considering oral small-molecule suitability.\n\n"
            f"{docking_note} From a developability perspective, {admet_summary}. These observations should be read as prioritization guidance for medicinal chemistry around "
            f"{target_label}, not as a clinical conclusion."
        )

    @staticmethod
    def _molecule_rows(target: Any, molecules: List[Any]) -> List[Any]:
        styles = ReportService._styles()
        story: List[Any] = []

        for index, molecule in enumerate(molecules, start=1):
            story.append(PageBreak())
            story.append(Paragraph(f"Compound Review: {ReportService._molecule_report_name(index, molecule)}", styles["MolHeading"]))
            story.append(Paragraph(f"Lead Candidate {index}", styles["MolSubtitle"]))
            story.append(ReportService._molecule_identity_table(index, molecule))
            story.append(Spacer(1, 0.15 * inch))

            image_buffer = ReportService._molecule_image(molecule.smiles)
            if image_buffer is not None:
                story.append(Image(image_buffer, width=3.0 * inch, height=2.2 * inch))
                story.append(Spacer(1, 0.15 * inch))
            else:
                story.append(Paragraph("2D structure image unavailable in this environment.", styles["MolSmall"]))

            story.append(Paragraph("ADMET Risk Table", styles["MolHeading"]))
            story.append(ReportService._admet_table(molecule.admet_scores or {}))
            docking_meta = (molecule.admet_scores or {}).get("_docking", {})
            model_source = (molecule.admet_scores or {}).get("model_source")
            if model_source:
                story.append(Paragraph(f"ADMET Source: {model_source}", styles["MolSmall"]))
            if docking_meta.get("is_mock"):
                story.append(
                    Paragraph(
                        "* Docking scores estimated via RDKit descriptor model. AutoDock Vina not available in this environment.",
                        styles["MolSmall"],
                    )
                )
            story.append(Spacer(1, 0.15 * inch))
            story.append(Paragraph("Professional Interpretation", styles["MolHeading"]))
            story.append(Paragraph(ReportService._compound_interpretation(target, molecule, index).replace("\n", "<br/><br/>"), styles["MolBody"]))
            story.append(Spacer(1, 0.25 * inch))

        return story

    @staticmethod
    def _provenance_table(target: Any, molecules: List[Any]) -> Table:
        docking_modes = []
        admet_sources = []
        for molecule in molecules:
            admet = molecule.admet_scores or {}
            docking_meta = admet.get("_docking", {})
            if isinstance(docking_meta, dict) and docking_meta.get("method"):
                method = str(docking_meta.get("method"))
                if method == "rdkit_fallback" or docking_meta.get("is_mock"):
                    docking_modes.append("rdkit_fallback")
                elif method == "vina":
                    docking_modes.append("vina")
                elif method == "legacy_stored_score":
                    docking_modes.append("legacy_stored_score")
                elif method == "not_run":
                    docking_modes.append("not_run")
            if admet.get("model_source"):
                admet_sources.append(admet["model_source"])

        rows = [
            ["Signal", "Source"],
            ["Target extraction", getattr(target, "gemini_source", None) or "unknown"],
            ["Druggability", "rule_based_breakdown"],
            ["ADMET", ", ".join(sorted(set(admet_sources))) if admet_sources else "unknown"],
            ["Docking", ", ".join(sorted(set(docking_modes))) if docking_modes else "unknown"],
        ]
        table = Table(rows, colWidths=[2.0 * inch, 4.0 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ]
            )
        )
        return table

    @staticmethod
    def _clinical_interpretation_text(target: Any, molecules: List[Any]) -> str:
        best = next((m for m in molecules if m.docking_score is not None), None)
        optimized = next((m for m in molecules if getattr(m, "is_optimized", False)), None)
        best_name = ReportService._molecule_report_name(molecules.index(best) + 1, best) if best else "the top-ranked compound"
        optimized_name = ReportService._molecule_report_name(molecules.index(optimized) + 1, optimized) if optimized else "no dedicated optimized lead"
        target_label = ReportService._target_label(target)
        target_function = getattr(target, "function", None) or "No mechanism summary was available from the enrichment step."
        return (
            f"This report should be interpreted as an early-stage computational assessment for {html.escape(target_label)}. "
            f"The target overview, mechanistic context, and compound triage are intended to support medicinal chemistry prioritization rather than make a therapeutic claim. "
            f"In the current enrichment record, the target function is summarized as follows: {html.escape(target_function)}\n\n"
            f"The most relevant immediate output is the relative ranking between compounds, especially the balance between docking affinity, synthetic accessibility, and ADMET liabilities.\n\n"
            f"Among the reviewed compounds, {best_name} represents the strongest currently recorded docking candidate in this batch for {html.escape(target_label)}. A stronger docking score can suggest improved geometric or energetic complementarity to the receptor model, "
            f"but the value should still be interpreted cautiously because docking remains highly dependent on receptor preparation, protonation state, and binding-site assumptions. "
            f"For that reason, any compound prioritized from this report should undergo confirmatory redocking, visual pose inspection, and if possible orthogonal scoring before wet-lab commitment.\n\n"
            f"The traffic-light system is designed for quick professional triage. Green values identify properties that are presently favorable within the internal thresholds, yellow values indicate an acceptable but cautionary range that may need scaffold tuning, "
            f"and red values flag liabilities likely to limit progression unless compensated by exceptional potency or tractable chemistry. In practical terms, a compound with green docking but red hepatotoxicity or CYP3A4 liability should not be considered a clean lead; "
            f"it is better described as an interesting scaffold requiring targeted remediation.\n\n"
            f"The presence of {optimized_name} in the set indicates that the workflow attempted lead refinement after initial ranking. That optimization step should be viewed as hypothesis generation: it proposes a direction for chemical improvement, but not a final clinical candidate. "
            f"The recommended next actions after this report are compound identity review, analog expansion around the strongest scaffold, explicit ADMET confirmation with higher-fidelity models or assays, and receptor-specific medicinal chemistry discussion focused on potency-selectivity-toxicity tradeoffs."
        )

    @staticmethod
    def _build_pdf(target: Any, molecules: List[Any], output: Any) -> None:
        styles = ReportService._styles()
        summary = ReportService._generate_target_summary(
            target.name,
            {
                "target_name": target.name,
                "uniprot_id": target.uniprot_id,
                "disease": getattr(target, "disease", None),
                "chembl_id": getattr(target, "chembl_id", None),
                "known_inhibitors": getattr(target, "known_inhibitors", None),
                "structure_count": getattr(target, "structure_count", None),
                "pdb_id": getattr(target, "pdb_id", None),
                "function": getattr(target, "function", None),
                "druggability_breakdown": getattr(target, "druggability_breakdown", None),
            },
        )

        doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        story: List[Any] = []

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        story.extend(
            [
                Paragraph("MolGenix Computational Lead Evaluation Report", styles["MolTitle"]),
                Paragraph(f"Target under review: {target.name}", styles["MolSubtitle"]),
                Paragraph(f"Generated: {generated_at}", styles["MolBody"]),
                Paragraph("Executive Overview", styles["MolHeading"]),
                Paragraph(
                    "This document summarizes target context, compound ranking, ADMET interpretation, and docking-based lead review in a format intended for medicinal chemistry and translational discussion.",
                    styles["MolBody"],
                ),
                ReportService._overview_metrics_table(target, molecules),
                Spacer(1, 0.18 * inch),
                Paragraph("Target Summary", styles["MolHeading"]),
                ReportService._target_summary_table(target),
                Spacer(1, 0.2 * inch),
                Paragraph(summary.replace("\n", "<br/>"), styles["MolBody"]),
                Spacer(1, 0.2 * inch),
                Paragraph("Evidence and Model Sources", styles["MolHeading"]),
                ReportService._provenance_table(target, molecules),
                Spacer(1, 0.2 * inch),
                KeepTogether(
                    [
                        Paragraph("Interpretation Matrix", styles["MolHeading"]),
                        Paragraph(
                            "The following ranges define how the green, yellow, and red classifications are assigned within the report.",
                            styles["MolBody"],
                        ),
                        ReportService._traffic_legend_table(),
                    ]
                ),
            ]
        )

        story.extend(ReportService._molecule_rows(target, molecules))
        story.append(PageBreak())
        story.append(Paragraph("Clinical and Medicinal Chemistry Interpretation", styles["MolHeading"]))
        story.append(Paragraph(ReportService._clinical_interpretation_text(target, molecules).replace("\n", "<br/><br/>"), styles["MolBody"]))

        doc.build(story)

    @staticmethod
    async def generate_report(
        target_id: str,
        db: Any,
        target_context: Any | None = None,
        molecule_ids: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Generate a PDF report for a target and persist the report record."""
        from app.models.molecule import Molecule
        from app.models.report import Report
        from app.models.target import Target

        target = db.query(Target).filter(Target.id == target_id).first()
        if not target:
            raise ValueError("Target not found")

        if not molecule_ids:
            raise ValueError("molecule_ids required for report generation")

        logger.info(
            "Generating report for target %s with %s molecule IDs: %s",
            target_id,
            len(molecule_ids),
            molecule_ids,
        )

        molecule_query = db.query(Molecule).filter(Molecule.target_id == target.id)
        molecule_uuids = [UUID(str(molecule_id)) for molecule_id in molecule_ids]
        molecule_query = molecule_query.filter(Molecule.id.in_(molecule_uuids))

        molecules = molecule_query.order_by(Molecule.docking_score.asc().nullslast(), Molecule.created_at.desc()).limit(5).all()
        if len(molecules) < 1:
            raise ValueError("No molecules found for target")

        report_target = await ReportService._ensure_target_context(target_context or target)
        molecules = await ReportService._ensure_molecule_annotations(report_target, molecules, db)
        buffer = io.BytesIO()
        ReportService._build_pdf(report_target, molecules, buffer)
        pdf_bytes = buffer.getvalue()

        ReportService.REPORT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        report_filename = f"{uuid4()}.pdf"
        report_path = ReportService.REPORT_STORAGE_DIR / report_filename
        report_path.write_bytes(pdf_bytes)

        report = Report(
            target_id=target.id,
            molecule_ids=[str(molecule_id) for molecule_id in molecule_ids],
            pdf_path=str(report_path),
            file_size_bytes=len(pdf_bytes),
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        return {
            "report_id": str(report.id),
            "pdf_url": f"/api/reports/{report.id}/download",
        }

    @staticmethod
    async def generate_report_bytes(
        target_id: str,
        db: Any,
        target_context: Any | None = None,
        molecule_ids: List[str] | None = None,
    ) -> bytes:
        """Generate a report PDF in memory without persisting it to disk."""
        from app.models.molecule import Molecule
        from app.models.target import Target

        target = db.query(Target).filter(Target.id == target_id).first()
        if not target:
            raise ValueError("Target not found")

        if not molecule_ids:
            raise ValueError("molecule_ids required for report generation")

        logger.info(
            "Generating report for target %s with %s molecule IDs: %s",
            target_id,
            len(molecule_ids),
            molecule_ids,
        )

        molecule_query = db.query(Molecule).filter(Molecule.target_id == target.id)
        molecule_uuids = [UUID(str(molecule_id)) for molecule_id in molecule_ids]
        molecule_query = molecule_query.filter(Molecule.id.in_(molecule_uuids))

        molecules = molecule_query.order_by(Molecule.docking_score.asc().nullslast(), Molecule.created_at.desc()).limit(5).all()
        if len(molecules) < 1:
            raise ValueError("No molecules found for target")

        report_target = await ReportService._ensure_target_context(target_context or target)
        molecules = await ReportService._ensure_molecule_annotations(report_target, molecules, db)
        buffer = io.BytesIO()
        ReportService._build_pdf(report_target, molecules, buffer)
        return buffer.getvalue()
