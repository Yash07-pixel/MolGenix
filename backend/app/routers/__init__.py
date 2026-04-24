"""FastAPI Route Handlers.

Routers are exposed lazily so importing one router does not force all router
dependencies to resolve immediately.
"""

from importlib import import_module

__all__ = ["targets_router", "molecules_router", "admet_router", "docking_router", "optimization_router", "reports_router"]


def __getattr__(name: str):
    if name == "targets_router":
        return import_module("app.routers.targets").router
    if name == "molecules_router":
        return import_module("app.routers.molecules").router
    if name == "admet_router":
        return import_module("app.routers.admet").router
    if name == "docking_router":
        return import_module("app.routers.docking").router
    if name == "optimization_router":
        return import_module("app.routers.optimization").router
    if name == "reports_router":
        return import_module("app.routers.reports").router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
