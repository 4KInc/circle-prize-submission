.PHONY: demo test rogue clean

# Run the full golden path demo (Phases 1-4) on Base Sepolia
demo:
	@./run_golden_path.sh

# Run unit tests
test:
	python3 -m pytest tests/test_circle_golden_path.py -v

# Run the rogue-agent containment demo (for demo video)
rogue:
	@./run_rogue_path.sh

# Clean generated artifacts
clean:
	rm -f /tmp/verigate-dashboard.html /tmp/verigate-compliance-report.pdf
