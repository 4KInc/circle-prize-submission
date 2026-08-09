.PHONY: demo test rogue dashboard clean

# Run the full golden path demo (Phases 1-4) on Base Sepolia
demo:
	@./run_golden_path.sh

# Run unit tests
test:
	python3 -m pytest tests/ -v

# Run the rogue-agent containment demo (for demo video)
rogue:
	@./run_rogue_path.sh

# Launch the live dashboard (opens browser)
dashboard:
	@echo "Starting Verigate Dashboard at http://localhost:8080"
	@python3 -m uvicorn app.server:app --host 0.0.0.0 --port 8080

# Clean generated artifacts
clean:
	rm -f /tmp/verigate-dashboard.html /tmp/verigate-compliance-report.pdf
