# Debian/Ubuntu Based
FROM python:3.11-slim

WORKDIR /app

# libgomp1 is required for some math libraries
# 'procps' is added so we can check cpuinfo
RUN apt-get update && \
    apt-get install -y libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to cache installation
COPY .config/requirements.txt .config/requirements.txt

# - remove 'polars' from the text file first to prevent pip from auto-installing the wrong one.
# - check /proc/cpuinfo for 'avx2' flags.
RUN \
    # Remove hardcoded polars to avoid conflict
    sed -i '/polars/d' .config/requirements.txt && \
    \
    # Install base requirements
    pip install --no-cache-dir -r .config/requirements.txt bcrypt && \
    \
    # Check CPU capabilities
    if grep -q "avx2" /proc/cpuinfo; then \
        echo "🚀 Modern CPU (AVX2) Detected: Installing standard Polars"; \
        pip install --no-cache-dir polars==1.30.0; \
    else \
        echo "🐢 Older CPU (No AVX2) Detected: Installing Polars LTS (CPU)"; \
        pip install --no-cache-dir polars-lts-cpu; \
    fi

# Copy the rest of the application
COPY . .
