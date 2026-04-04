"""
Vercel Python entrypoint.
Reuses backend/motor.py and exposes the same API under /api/*.
"""

import sys
from pathlib import Path
from fastapi import FastAPI

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from motor import app as backend_app

app = FastAPI(title="Hotel Demo API Adapter")
app.include_router(backend_app.router, prefix="/api")


@app.get("/api")
def api_root():
    return {"ok": True, "service": "hotel-demo-backend"}
