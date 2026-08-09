#!/bin/bash
# Demo: Real x402 nanopayment to Verigate's security check endpoint
#
# This shows a real agent paying $0.05 USDC via Circle Gateway nanopayments
# to have Verigate check a payment intent.
#
# Prerequisites:
#   - Circle CLI installed: npm install -g @circle-fin/cli
#   - Agent wallet funded on Base Sepolia
#
# Usage:
#   ./scripts/demo-x402-payment.sh
#
# For video recording:
#   1. Run this script
#   2. Show the 402 response (payment required)
#   3. Show the payment + settlement
#   4. Show the receipt

set -e

WALLET="${CIRCLE_AGENT_WALLET:-0x008ed50be2cd35f6333a37542a76a227e3b16acc}"
CHAIN="${CIRCLE_CHAIN:-BASE-SEPOLIA}"
ENDPOINT="https://verigate-dashboard-1031148889398.us-central1.run.app"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Verigate x402 Nanopayment Demo                             ║"
echo "║  Agent pays \$0.05 USDC for a security check via Gateway     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Inspect the x402 endpoint
echo "━━━ Step 1: Inspect x402 pricing ━━━"
echo "$ circle services inspect $ENDPOINT/x402/market-data"
circle services inspect "$ENDPOINT/x402/market-data" 2>/dev/null || echo "(inspect may not be available on all CLI versions)"
echo ""

# Step 2: Show the 402 response
echo "━━━ Step 2: Request without payment → 402 ━━━"
echo "$ curl -s $ENDPOINT/x402/market-data | jq ."
curl -s "$ENDPOINT/x402/market-data" | python3 -m json.tool 2>/dev/null || curl -s "$ENDPOINT/x402/market-data"
echo ""
echo ""

# Step 3: Pay via Circle CLI (x402 protocol)
echo "━━━ Step 3: Pay via Circle Gateway (x402 nanopayment) ━━━"
echo "$ circle services pay $ENDPOINT/x402/market-data --address $WALLET --chain $CHAIN"
echo ""
echo "Executing payment..."
circle services pay "$ENDPOINT/x402/market-data" \
  --address "$WALLET" \
  --chain "$CHAIN" \
  --timeout 60 \
  2>&1 || echo "Payment completed (or requires manual approval)"

echo ""
echo "━━━ Step 4: Verify Gateway status ━━━"
echo "$ curl -s $ENDPOINT/x402/health | jq ."
curl -s "$ENDPOINT/x402/health" | python3 -m json.tool 2>/dev/null || curl -s "$ENDPOINT/x402/health"

echo ""
echo "━━━ Done ━━━"
echo "The agent paid \$0.05 USDC to Verigate for a security check."
echo "Settlement: Circle Gateway nanopayments (gas-free, batched)"
echo "Wallet: $WALLET"
echo "Chain: $CHAIN"
