"""OFAC SDN sanctions screening — static seed + live feed sync.

The risk engine screens payees against OFAC's Specially Designated
Nationals (SDN) list. This module provides that list two ways:

  1. STATIC_OFAC_ETH — a small, hand-verified seed of genuinely
     OFAC-listed Ethereum addresses. Always available, no network
     needed. Used as the fallback and as the floor of the active set.

  2. Live sync — refresh() fetches OFAC's official SDN export, parses
     every "Digital Currency Address - ETH" entry, and merges it into
     the active set. The snapshot records the feed's publish date and a
     content digest so a receipt can *attest* which version of the list
     a decision was screened against.

Design guarantees:
  - Importing this module NEVER touches the network. refresh() is the
    only network path and must be called explicitly (or by the daemon).
  - Screening never blocks on I/O: scoring reads an in-memory frozenset.
  - If a fetch fails or is never run, the active set == the static seed,
    and feed_metadata() honestly reports source="static-seed".
  - Exact-match screening only. No prefix/substring heuristics (those
    produce false positives that wrongly block legitimate counterparties).

Feed: https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/sdn.xml
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("circle.sanctions")

# Official OFAC SDN export (the legacy www.treasury.gov URL 302-redirects here).
OFAC_SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/sdn.xml"

# GCS/local cache object path for the parsed address set.
SANCTIONS_CACHE_PATH = "sanctions/ofac_sdn_eth.json"

# ── Static, hand-verified seed (genuinely OFAC-listed ETH addresses) ──
# Lowercased for exact-match comparison. Verified present in the live
# feed's "Digital Currency Address - ETH" entries.
STATIC_OFAC_ETH = frozenset({
    # Tornado Cash — OFAC designated 2022-08-08
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",  # TC: donation
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # TC: router
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",  # TC: pool
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # TC: pool
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",  # TC: 10 ETH pool
    "0xa160cdab225685da1d56aa342ad8841c3b53f291",  # TC: 100 ETH pool
    "0xf60dd140cff0706bae9cd734ac3ae76ad9ebc32a",  # TC: proxy
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659",  # TC: pool
    # Lazarus Group / DPRK — OFAC designated
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",  # Ronin bridge exploiter
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",  # Lazarus
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073",  # Lazarus
})

# Matches an ETH digital-currency-address id block in the SDN XML,
# tolerant of the namespaced, pretty-printed layout:
#   <idType>Digital Currency Address - ETH</idType>
#   <idNumber>0x…40 hex…</idNumber>
_ETH_ID_RE = re.compile(
    r"Digital Currency Address - ETH\s*</idType>\s*<idNumber>\s*(0x[0-9a-fA-F]{40})\s*</idNumber>",
    re.IGNORECASE,
)
_PUBLISH_DATE_RE = re.compile(r"<Publish_Date>\s*([^<]+?)\s*</Publish_Date>", re.IGNORECASE)
_RECORD_COUNT_RE = re.compile(r"<Record_Count>\s*([0-9]+)\s*</Record_Count>", re.IGNORECASE)


def _digest(addresses: frozenset[str]) -> str:
    joined = ",".join(sorted(addresses)).encode()
    return "sha256:" + hashlib.sha256(joined).hexdigest()


@dataclass(frozen=True)
class SanctionsSnapshot:
    """An immutable view of the active sanctions set and its provenance."""
    addresses: frozenset[str]
    source: str                    # "static-seed" | "ofac-sdn-live"
    published: str | None          # feed Publish_Date, if live
    fetched_at: str | None         # when we fetched it, ISO-8601
    entry_count: int               # number of ETH addresses in the active set
    digest: str                    # sha256 over sorted active addresses

    def metadata(self) -> dict:
        """Provenance dict suitable for embedding in a signed receipt."""
        return {
            "list": "OFAC-SDN-ETH",
            "source": self.source,
            "published": self.published,
            "fetched_at": self.fetched_at,
            "entry_count": self.entry_count,
            "digest": self.digest,
        }


def _static_snapshot() -> SanctionsSnapshot:
    return SanctionsSnapshot(
        addresses=STATIC_OFAC_ETH,
        source="static-seed",
        published=None,
        fetched_at=None,
        entry_count=len(STATIC_OFAC_ETH),
        digest=_digest(STATIC_OFAC_ETH),
    )


# Module singleton state, guarded by a lock. Starts as the static seed.
_lock = threading.Lock()
_snapshot: SanctionsSnapshot = _static_snapshot()


def active_addresses() -> frozenset[str]:
    """The current active sanctions set (static seed ∪ any live sync)."""
    return _snapshot.addresses


def snapshot() -> SanctionsSnapshot:
    """The current snapshot including provenance."""
    return _snapshot


def feed_metadata() -> dict:
    """Provenance of the active list, for receipt attestation."""
    return _snapshot.metadata()


def is_sanctioned(address: str) -> bool:
    """Exact-match screen against the active set (case-insensitive)."""
    return address.lower().strip() in _snapshot.addresses


def parse_sdn_xml(text: str) -> tuple[frozenset[str], str | None, int | None]:
    """Parse OFAC SDN XML text → (eth_addresses, publish_date, record_count).

    Pure function — no I/O. Deterministic. Safe to unit-test with a fixture.
    """
    addresses = {m.group(1).lower() for m in _ETH_ID_RE.finditer(text)}
    pub_m = _PUBLISH_DATE_RE.search(text)
    cnt_m = _RECORD_COUNT_RE.search(text)
    published = pub_m.group(1) if pub_m else None
    record_count = int(cnt_m.group(1)) if cnt_m else None
    return frozenset(addresses), published, record_count


def _default_fetcher(timeout: float) -> str:
    import httpx
    resp = httpx.get(OFAC_SDN_URL, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def refresh(fetcher=None, timeout: float = 90.0, persist: bool = True) -> SanctionsSnapshot:
    """Fetch + parse the live OFAC SDN feed and merge into the active set.

    The active set is always seed ∪ live, so a live sync can only ADD
    addresses, never drop a known-bad one. On any failure the current
    snapshot is preserved and returned unchanged (fail-safe).

    Args:
        fetcher: callable(timeout)->str returning SDN XML. Defaults to httpx.
                 Injectable for tests (no network).
        timeout: fetch timeout in seconds.
        persist: write the parsed set to the GCS/local cache on success.
    """
    global _snapshot
    fetch = fetcher or _default_fetcher
    try:
        text = fetch(timeout)
        eth, published, _record_count = parse_sdn_xml(text)
        if not eth:
            logger.warning("OFAC refresh parsed 0 ETH addresses — keeping current snapshot")
            return _snapshot
        merged = frozenset(STATIC_OFAC_ETH | eth)
        snap = SanctionsSnapshot(
            addresses=merged,
            source="ofac-sdn-live",
            published=published,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            entry_count=len(merged),
            digest=_digest(merged),
        )
        with _lock:
            _snapshot = snap
        logger.info(
            "OFAC SDN refresh: %d ETH addresses (published %s), digest %s",
            len(merged), published, snap.digest[:20],
        )
        if persist:
            _persist_cache(snap)
        return snap
    except Exception as e:  # noqa: BLE001 — fail-safe, never break scoring
        logger.warning("OFAC SDN refresh failed (%s) — keeping current snapshot", e)
        return _snapshot


def _persist_cache(snap: SanctionsSnapshot) -> None:
    payload = {
        "addresses": sorted(snap.addresses),
        "source": snap.source,
        "published": snap.published,
        "fetched_at": snap.fetched_at,
        "entry_count": snap.entry_count,
        "digest": snap.digest,
    }
    try:
        from app import storage
        storage.store_json(SANCTIONS_CACHE_PATH, payload)
    except Exception as e:  # noqa: BLE001
        logger.debug("Sanctions cache persist skipped: %s", e)


def load_cache() -> bool:
    """Load a previously-synced set from the GCS/local cache, if present.

    Returns True if a cached snapshot was loaded. Never raises.
    """
    global _snapshot
    try:
        from app import storage
        payload = storage.load_json(SANCTIONS_CACHE_PATH)
        if not payload or not payload.get("addresses"):
            return False
        merged = frozenset(STATIC_OFAC_ETH | {a.lower() for a in payload["addresses"]})
        snap = SanctionsSnapshot(
            addresses=merged,
            source=payload.get("source", "ofac-sdn-live"),
            published=payload.get("published"),
            fetched_at=payload.get("fetched_at"),
            entry_count=len(merged),
            digest=_digest(merged),
        )
        with _lock:
            _snapshot = snap
        logger.info("Loaded %d sanctioned ETH addresses from cache", len(merged))
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("Sanctions cache load skipped: %s", e)
        return False


_refresher_started = False


def start_background_refresh(interval_hours: float = 12.0, initial_delay: float = 5.0) -> None:
    """Start a daemon thread that refreshes the SDN list periodically.

    Idempotent — calling more than once is a no-op. First tries the cache
    for an immediate warm start, then syncs from the live feed.
    """
    global _refresher_started
    if _refresher_started:
        return
    _refresher_started = True

    def _loop() -> None:
        load_cache()
        time.sleep(initial_delay)
        while True:
            refresh()
            time.sleep(max(interval_hours, 0.1) * 3600)

    t = threading.Thread(target=_loop, name="ofac-sdn-refresher", daemon=True)
    t.start()
    logger.info("OFAC SDN background refresher started (every %.1fh)", interval_hours)
