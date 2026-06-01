# Dockerfile for Idealista Bot
# Using official Playwright image which includes browsers and dependencies
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Suppress interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Madrid

# Install VNC server + git (for noVNC clone)
RUN apt-get update && apt-get install -y --no-install-recommends \
    x11vnc \
    xvfb \
    fluxbox \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone noVNC for browser-based CAPTCHA solving
RUN git clone --depth=1 https://github.com/novnc/noVNC.git /novnc

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Patchright's patched Chromium (system deps already in base image)
RUN patchright install chromium

# Copy application files
COPY . .

# Create directories for data persistence
RUN mkdir -p /app/listings /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Madrid
ENV DISPLAY=:99

# Run the scheduler script
CMD ["/bin/bash", "/app/docker_entrypoint.sh"]
