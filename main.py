"""
Vercel entrypoint for FastAPI backend.
Imports and exposes the FastAPI app from backend/motor.py
"""

import sys
from pathlib import Path

# Agregar backend al path para los imports
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from motor import app

__all__ = ["app"]
