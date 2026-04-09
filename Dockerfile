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

# Install directly
RUN pip install --no-cache-dir -r .config/requirements.txt bcrypt

# Copy the rest of the application
COPY . .
