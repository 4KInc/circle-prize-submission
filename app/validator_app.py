"""Standalone Evidence Validator service.

Runs independently from Verigate — its own FastAPI app, own wallet, own keys.
Verigate pays this service $0.02 USDC per validation via x402 protocol.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.validator import router as validator_router

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

app = FastAPI(
    title="Verigate Evidence Validator",
    description="Independent evidence validation service. Receives $0.02 USDC per check.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(validator_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "evidence-validator"}
