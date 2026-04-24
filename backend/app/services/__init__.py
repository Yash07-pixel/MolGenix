"""Business Logic Layer - Services.

Imports stay lazy so optional dependencies for one service do not break
unrelated modules during import.
"""

from importlib import import_module

__all__ = ["TargetEnrichmentService", "MoleculeGenerationService", "ADMETService", "DockingService", "OptimizationService", "ReportService", "GeminiService"]


def __getattr__(name: str):
    if name == "TargetEnrichmentService":
        return import_module("app.services.target_service").TargetEnrichmentService
    if name == "MoleculeGenerationService":
        return import_module("app.services.molecule_service").MoleculeGenerationService
    if name == "ADMETService":
        return import_module("app.services.admet_service").ADMETService
    if name == "DockingService":
        return import_module("app.services.docking_service").DockingService
    if name == "OptimizationService":
        return import_module("app.services.optimization_service").OptimizationService
    if name == "ReportService":
        return import_module("app.services.report_service").ReportService
    if name == "GeminiService":
        return import_module("app.services.gemini_service").GeminiService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
