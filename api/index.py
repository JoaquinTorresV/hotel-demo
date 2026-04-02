"""
Vercel entrypoint for FastAPI backend (api/index.py)
This is a standard Vercel location for FastAPI apps
"""

import sys
from pathlib import Path

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# Importar y exponer la app FastAPI
from motor import app

__all__ = ["app"]
