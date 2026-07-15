FROM python:3.11-slim

# Install basic build tools and library headers for postgresql psycopg2 driver stability
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure start script has executable rights
RUN chmod +x start.sh

# Ensure python output is sent straight to terminal (useful for docker logging)
ENV PYTHONUNBUFFERED=1

# Set the command to execute our start script
CMD ["./start.sh"]
