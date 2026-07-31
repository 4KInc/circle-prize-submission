#!/usr/bin/env bash
# run_golden_path.sh — Execute the full Verigate golden path demo unattended.
#
# Runs Phases 1-4 on Base Sepolia and prints every explorer URL.
# Requires: Circle CLI authenticated (testnet), Python 3.12+, GEMINI_API_KEY set.
#
# Usage:
#   ./run_golden_path.sh              # Default: Base Sepolia
#   CIRCLE_CHAIN=BASE ./run_golden_path.sh  # Mainnet (requires mainnet auth + funded wallet)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Preflight checks ─────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════════════"
echo "Verigate Golden Path — Circle Agentic Economy Prize Demo"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi
echo "[preflight] Python: $(python3 --version)"

# Check Circle CLI
CIRCLE_BIN="${HOME}/.local/bin/circle"
if [ ! -f "$CIRCLE_BIN" ]; then
    CIRCLE_BIN="$(command -v circle 2>/dev/null || true)"
fi
if [ -z "$CIRCLE_BIN" ]; then
    echo "ERROR: Circle CLI not found. Install: npm install -g @circle-fin/cli"
    exit 1
fi
export PATH="${HOME}/.local/bin:$PATH"
echo "[preflight] Circle CLI: $(CIRCLE_ACCEPT_TERMS=1 circle --version 2>/dev/null)"

# Check Circle auth
if ! CIRCLE_ACCEPT_TERMS=1 circle wallet status 2>&1 | grep -q "VALID"; then
    echo "ERROR: Circle CLI not authenticated. Run: circle wallet login <email> --testnet"
    exit 1
fi
echo "[preflight] Circle auth: VALID"

# Check for Gemini API key
if [ -z "${GEMINI_API_KEY:-}" ] && [ -z "${GOOGLE_API_KEY:-}" ]; then
    echo "WARNING: No GEMINI_API_KEY or GOOGLE_API_KEY set. Gemini agent will use mock."
fi

# ── Run unit tests ────────────────────────────────────────────────────
echo ""
echo "[tests] Running unit tests..."
python3 -m pytest tests/test_circle_golden_path.py -v --tb=short 2>&1 | tail -5
echo ""

# ── Run golden path ──────────────────────────────────────────────────
echo "[golden-path] Starting Phases 1-4..."
echo ""
python3 -m circle.golden_path

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "Demo artifacts:"
echo "  Dashboard:  /tmp/verigate-dashboard.html"
echo "  PDF Report: /tmp/verigate-compliance-report.pdf"
echo "═══════════════════════════════════════════════════════════════════"
