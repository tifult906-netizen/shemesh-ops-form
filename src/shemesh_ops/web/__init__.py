"""Web UI for the Shemesh operation-form workflow.

Run with:
    uvicorn shemesh_ops.web.app:app --reload
or via the module entrypoint:
    python -m shemesh_ops.web
"""
from .app import app

__all__ = ["app"]
