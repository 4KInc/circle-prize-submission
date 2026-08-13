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

# Install Python deps
RUN pip install --no-cache-dir cryptography PyJWT PyYAML google-genai reportlab fastapi "uvicorn[standard]" httpx google-cloud-storage

ENV PORT=8080
ENV CIRCLE_ACCEPT_TERMS=1

EXPOSE 8080

CMD ["./entrypoint.sh"]
