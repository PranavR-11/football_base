# MCP Server Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MCP code
COPY mcp/ ./mcp/
COPY data/ ./data/

# Expose MCP port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/.well-known/mcp/health || exit 1

# Run MCP server
CMD ["uvicorn", "mcp.mcp_server:app", "--host", "0.0.0.0", "--port", "8080"]
