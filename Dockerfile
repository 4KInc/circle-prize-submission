FROM python:3.13-slim

WORKDIR /app

# Install Node.js for Circle CLI
RUN apt-get update && apt-get install -y --no-install-recommends curl git && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @circle-fin/cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project
COPY pyproject.toml .
COPY circle/ circle/
COPY verigate/ verigate/
COPY app/ app/
COPY reference/ reference/
COPY tests/ tests/
COPY engine/ engine/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Fail the BUILD if the engine submodule was not checked out.
# `COPY engine/ engine/` silently succeeds on an empty directory, so without
# this the image builds fine and then dies at container start with a bare
# ModuleNotFoundError — surfacing as a Cloud Run health-check timeout during
# deploy, which is both slow to diagnose and expensive to hit in production.
RUN test -f engine/gateway/__init__.py || ( \
      echo "" >&2; \
      echo "BUILD FAILED: engine/ submodule is not checked out." >&2; \
      echo "engine/gateway/__init__.py is missing, so the gateway package" >&2; \
      echo "(canonicalize, merkle, policy, receipts, tokens) is unavailable." >&2; \
      echo "" >&2; \
      echo "  Fix:  git submodule update --init --recursive" >&2; \
      echo "" >&2; \
      exit 1 )

# Install Python deps
RUN pip install --no-cache-dir cryptography PyJWT PyYAML google-genai reportlab fastapi "uvicorn[standard]" httpx google-cloud-storage && \
    pip install --no-cache-dir "mcp[cli]==1.23.3"

ENV PORT=8080
ENV CIRCLE_ACCEPT_TERMS=1

EXPOSE 8080

CMD ["./entrypoint.sh"]
