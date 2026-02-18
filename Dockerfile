FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and requirements.txt first for better caching
COPY pyproject.toml requirements.txt ./

# Install Python dependencies using requirements.txt (more reliable)
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Install the package itself so pdf2html_api is importable
RUN pip install --no-cache-dir .

# Expose port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "src.pdf2html_api.main:app", "--host", "0.0.0.0", "--port", "8000"] 