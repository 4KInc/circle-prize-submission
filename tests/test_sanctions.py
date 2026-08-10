"""Unit tests for the OFAC SDN sanctions module (circle/sanctions.py).

Network-free: refresh() is always driven by an injected fetcher that
returns a fixture string, never httpx. Verifies the parser, the
seed ∪ live merge, provenance metadata, and the fail-safe fallback.
"""

from __future__ import annotations

import circle.sanctions as sanctions


# A minimal, realistic SDN XML fixture: namespaced, pretty-printed,
# containing two ETH addresses (one already in the static seed, one new)
# plus a BTC entry and a non-currency record that must be ignored.
SDN_XML_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<sdnList xmlns="https://www.treasury.gov/ofac/downloads/sanctions/1.0">
  <publshInformation>
    <Publish_Date>08/07/2026</Publish_Date>
    <Record_Count>19199</Record_Count>
  </publshInformation>
  <sdnEntry>
    <uid>10001</uid>
    <idList>
      <id>
        <idType>Digital Currency Address - ETH</idType>
        <idNumber>0x722122dF12D4e14e13Ac3b6895a86e84145b6967</idNumber>
      </id>
    </idList>
  </sdnEntry>
  <sdnEntry>
    <uid>10002</uid>
    <idList>
      <id>
        <idType>Digital Currency Address - ETH</idType>
        <idNumber>0x1111111111111111111111111111111111111111</idNumber>
      </id>
      <id>
        <idType>Digital Currency Address - BTC</idType>
        <idNumber>1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2</idNumber>
      </id>
    </idList>
  </sdnEntry>
</sdnList>
"""


def _fixture_fetcher(_timeout):
    return SDN_XML_FIXTURE


def test_parse_sdn_xml_extracts_eth_only():
    eth, published, record_count = sanctions.parse_sdn_xml(SDN_XML_FIXTURE)
    assert "0x722122df12d4e14e13ac3b6895a86e84145b6967" in eth  # lowercased
    assert "0x1111111111111111111111111111111111111111" in eth
    # BTC address must NOT be captured
    assert all(a.startswith("0x") for a in eth)
    assert len(eth) == 2
    assert published == "08/07/2026"
    assert record_count == 19199


def test_parse_sdn_xml_empty_input():
    eth, published, record_count = sanctions.parse_sdn_xml("<sdnList></sdnList>")
    assert eth == frozenset()
    assert published is None
    assert record_count is None


def test_static_seed_is_the_default_snapshot():
    snap = sanctions._static_snapshot()
    assert snap.source == "static-seed"
    assert snap.published is None
    assert snap.entry_count == len(sanctions.STATIC_OFAC_ETH)
    assert snap.digest.startswith("sha256:")


def test_refresh_merges_seed_and_live(monkeypatch):
    # Isolate module singleton so the test is order-independent.
    monkeypatch.setattr(sanctions, "_snapshot", sanctions._static_snapshot())
    snap = sanctions.refresh(fetcher=_fixture_fetcher, persist=False)

    assert snap.source == "ofac-sdn-live"
    assert snap.published == "08/07/2026"
    assert snap.fetched_at is not None
    # The brand-new live address is now screened.
    assert "0x1111111111111111111111111111111111111111" in snap.addresses
    # Every static-seed address is preserved (live can only ADD).
    assert sanctions.STATIC_OFAC_ETH <= snap.addresses
    # entry_count == size of the merged set.
    assert snap.entry_count == len(snap.addresses)


def test_refresh_updates_module_state_and_is_sanctioned(monkeypatch):
    monkeypatch.setattr(sanctions, "_snapshot", sanctions._static_snapshot())
    sanctions.refresh(fetcher=_fixture_fetcher, persist=False)
    # Case-insensitive exact match against the newly merged set.
    assert sanctions.is_sanctioned("0x1111111111111111111111111111111111111111")
    assert sanctions.is_sanctioned("0x1111111111111111111111111111111111111111".upper())
    assert not sanctions.is_sanctioned("0x2222222222222222222222222222222222222222")


def test_refresh_failsafe_keeps_current_snapshot(monkeypatch):
    monkeypatch.setattr(sanctions, "_snapshot", sanctions._static_snapshot())
    before = sanctions.snapshot()

    def _boom(_timeout):
        raise RuntimeError("network down")

    snap = sanctions.refresh(fetcher=_boom, persist=False)
    # Unchanged, still the static seed — scoring never breaks.
    assert snap is before
    assert snap.source == "static-seed"


def test_refresh_empty_parse_keeps_current_snapshot(monkeypatch):
    monkeypatch.setattr(sanctions, "_snapshot", sanctions._static_snapshot())
    before = sanctions.snapshot()
    snap = sanctions.refresh(fetcher=lambda _t: "<sdnList></sdnList>", persist=False)
    assert snap is before  # 0 parsed addresses → keep seed, don't wipe


def test_feed_metadata_shape():
    md = sanctions.feed_metadata()
    assert md["list"] == "OFAC-SDN-ETH"
    assert md["source"] in ("static-seed", "ofac-sdn-live")
    assert "digest" in md and md["digest"].startswith("sha256:")
    assert "entry_count" in md


def test_digest_is_order_independent():
    a = sanctions._digest(frozenset({"0xaaa", "0xbbb"}))
    b = sanctions._digest(frozenset({"0xbbb", "0xaaa"}))
    assert a == b
