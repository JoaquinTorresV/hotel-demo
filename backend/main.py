"""
Vercel entrypoint for FastAPI backend.
Imports and exposes the FastAPI app from motor.py
"""

from motor import app

__all__ = ["app"]
