# PDF2HTML API

Convert PDF pages to HTML using OpenAI Vision API via HTTP.

## Features

- Convert PDF files to HTML using OpenAI's Vision API
- Support for multiple CSS layout modes (grid, columns, single)
- Configurable DPI and model parameters
- FastAPI-based REST API with automatic documentation
- Docker containerization for easy deployment

## Quick Start

### Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd pdf2llm2html
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e ".[dev]"
```

4. Set up environment variables:
```bash
cp env.example .env
# Edit .env with your OpenAI API key
```

5. Run the API:
```bash
python run_api.py
```

The API will be available at `http://localhost:8000` with documentation at `http://localhost:8000/docs`.

### Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t pdf2html-api .
docker run -p 8000:8000 -e OPENAI_API_KEY=your-key pdf2html-api
```

## API Usage

### Convert PDF to HTML

```bash
curl -X POST "http://localhost:8000/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_url": "https://example.com/document.pdf",
    "model": "gpt-4o-mini",
    "dpi": 200,
    "css_mode": "grid"
  }'
```

### Health Check

```bash
curl http://localhost:8000/health
```

## CI/CD Pipeline

This project includes a comprehensive CI/CD pipeline with the following features:

### GitHub Actions Workflows

1. **CI Pipeline** (`.github/workflows/ci.yml`)
   - Runs on PRs to `main` and `staging` branches
   - Executes tests, linting, and security checks
   - Supports multiple Python versions (3.11, 3.12)
   - Generates test coverage reports

2. **Staging Deployment** (`.github/workflows/deploy-staging.yml`)
   - Triggers on pushes to `staging` branch
   - Builds and pushes Docker image to Docker Hub
   - Deploys to staging environment on Hetzner server

3. **Production Deployment** (`.github/workflows/deploy-production.yml`)
   - Triggers on pushes to `main` branch
   - Deploys to production environment on Hetzner server
   - Includes health checks and notifications

### Server Setup

1. **Initial Server Setup**
```bash
# On your Hetzner server
wget https://raw.githubusercontent.com/your-repo/pdf2llm2html/main/deployment/setup-server.sh
chmod +x setup-server.sh
./setup-server.sh
```

2. **Configure Environment Variables**
   - Update `/opt/pdf2html-api-staging/.env`
   - Update `/opt/pdf2html-api-production/.env`
   - Configure Traefik with your domain

3. **DNS Configuration**
   - Point `staging.pdf2html.yourdomain.com` to staging server
   - Point `api.pdf2html.yourdomain.com` to production server

### Required GitHub Secrets

Configure these secrets in your GitHub repository:

- `OPENAI_API_KEY`: Your OpenAI API key
- `DOCKER_USERNAME`: Your Docker Hub username
- `DOCKER_PASSWORD`: Your Docker Hub password/token
- `HETZNER_STAGING_HOST`: Staging server IP/hostname
- `HETZNER_PRODUCTION_HOST`: Production server IP/hostname
- `HETZNER_USERNAME`: SSH username for Hetzner servers
- `HETZNER_SSH_KEY`: SSH private key for Hetzner servers

### Manual Deployment

Use the deployment script for manual operations:

```bash
# Deploy to staging
./deployment/deploy.sh staging deploy

# Deploy to production
./deployment/deploy.sh production deploy

# Rollback staging
./deployment/deploy.sh staging rollback

# Check status
./deployment/deploy.sh staging status

# View logs
./deployment/deploy.sh staging logs
```

### Monitoring

The production environment includes monitoring with Prometheus and Grafana:

```bash
# Start monitoring stack
cd /opt/monitoring
docker-compose -f monitoring.yml up -d
```

Access monitoring at:
- Grafana: `https://grafana.yourdomain.com` (admin/admin123)
- Prometheus: `https://monitoring.yourdomain.com`

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/test_api.py -v
```

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

### Adding Dependencies

Update `pyproject.toml` and install:

```bash
pip install -e ".[dev]"
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `ENVIRONMENT` | Environment name | `development` |

## Architecture

- **FastAPI**: Web framework for the REST API
- **OpenAI Vision API**: Converts PDF pages to HTML
- **PyMuPDF**: PDF processing and image rendering
- **Docker**: Containerization for deployment
- **Traefik**: Reverse proxy with SSL termination
- **Prometheus/Grafana**: Monitoring and alerting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

MIT License - see LICENSE file for details. 