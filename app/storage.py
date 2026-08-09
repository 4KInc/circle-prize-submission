"""GCS persistence for Verigate receipts, artifacts, and proof bundles.

Stores each demo run as a timestamped proof bundle in Cloud Storage,
enabling retrieval for insurance claims, carrier underwriting, and audits.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("app.storage")

BUCKET_NAME = os.environ.get("VERIGATE_BUCKET", "verigate-proof-bundles")
GCS_ENABLED = os.environ.get("VERIGATE_GCS_ENABLED", "1") == "1"

_client = None
_bucket = None


def _get_bucket():
    global _client, _bucket
    if _bucket is not None:
        return _bucket
    try:
        from google.cloud import storage
        _client = storage.Client()
        _bucket = _client.bucket(BUCKET_NAME)
        if not _bucket.exists():
            _bucket.create(location="us-central1")
            logger.info("Created GCS bucket: %s", BUCKET_NAME)
        return _bucket
    except Exception as e:
        logger.warning("GCS unavailable: %s", e)
        return None


def store_proof_bundle(bundle: dict, run_id: str) -> str | None:
    """Store a proof bundle to GCS. Returns the GCS object path or None."""
    if not GCS_ENABLED:
        return None
    bucket = _get_bucket()
    if bucket is None:
        return None
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = f"bundles/{ts}_{run_id}.json"
        blob = bucket.blob(path)
        blob.upload_from_string(
            json.dumps(bundle, default=str, indent=2),
            content_type="application/json",
        )
        logger.info("Stored proof bundle: gs://%s/%s", BUCKET_NAME, path)
        return f"gs://{BUCKET_NAME}/{path}"
    except Exception as e:
        logger.warning("Failed to store proof bundle: %s", e)
        return None


def store_receipt(receipt: dict, run_id: str, index: int) -> str | None:
    """Store an individual receipt to GCS."""
    if not GCS_ENABLED:
        return None
    bucket = _get_bucket()
    if bucket is None:
        return None
    try:
        receipt_hash = receipt.get("receipt_hash", f"idx_{index}")[:16]
        path = f"receipts/{run_id}/{index:03d}_{receipt_hash}.json"
        blob = bucket.blob(path)
        blob.upload_from_string(
            json.dumps(receipt, default=str, indent=2),
            content_type="application/json",
        )
        return f"gs://{BUCKET_NAME}/{path}"
    except Exception as e:
        logger.warning("Failed to store receipt: %s", e)
        return None


def list_bundles(limit: int = 50) -> list[dict]:
    """List recent proof bundles from GCS."""
    if not GCS_ENABLED:
        return []
    bucket = _get_bucket()
    if bucket is None:
        return []
    try:
        blobs = list(bucket.list_blobs(prefix="bundles/", max_results=limit))
        blobs.sort(key=lambda b: b.name, reverse=True)
        return [
            {
                "name": b.name,
                "url": f"gs://{BUCKET_NAME}/{b.name}",
                "created": b.time_created.isoformat() if b.time_created else None,
                "size": b.size,
            }
            for b in blobs
        ]
    except Exception as e:
        logger.warning("Failed to list bundles: %s", e)
        return []


def get_bundle(path: str) -> dict | None:
    """Retrieve a proof bundle from GCS by its object path."""
    if not GCS_ENABLED:
        return None
    bucket = _get_bucket()
    if bucket is None:
        return None
    try:
        # Accept either "bundles/..." or "gs://bucket/bundles/..."
        obj_path = path.replace(f"gs://{BUCKET_NAME}/", "")
        blob = bucket.blob(obj_path)
        data = blob.download_as_text()
        return json.loads(data)
    except Exception as e:
        logger.warning("Failed to get bundle %s: %s", path, e)
        return None
