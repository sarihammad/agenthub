# Multi-stage build for production-ready image
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies to a local directory
RUN pip install --no-cache-dir --prefix=/install .

# Runtime stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH"

WORKDIR /app

# Create non-root user
RUN groupadd -r agenthub && useradd -r -g agenthub -u 10001 agenthub

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY src/ ./src/

# Create directories with proper permissions
RUN mkdir -p /tmp/prometheus_multiproc_dir && \
    chown -R agenthub:agenthub /app /tmp/prometheus_multiproc_dir

# Switch to non-root user
USER 10001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "agenthub.server"]
