# api/Dockerfile — multi-stage, builds a venv in the builder stage
FROM python:3.11-slim as builder

# Install build deps needed for compiling binary wheels (libgomp1 required by faiss/OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /tmp/build
# Copy only requirements first to leverage layer caching
COPY api/requirements.txt ./requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Final minimal runtime image
FROM python:3.11-slim

# Runtime deps (libgomp for faiss, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# App working dir
WORKDIR /app

# Copy application code (copy the whole api folder and scripts)
COPY api/ ./api/
COPY scripts/ ./scripts/
# If mcp is separate:
COPY mcp/ ./mcp/
# create data+models+cache dirs (mount them at runtime)
RUN mkdir -p /app/data /app/data/vectorstore /app/models /app/cache

# Expose port
EXPOSE 8000

# Lightweight healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start (use uvicorn, set env var for production tuning if needed)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]