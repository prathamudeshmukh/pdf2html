# PDF2HTML API

Convert PDF pages to HTML using OpenAI Vision API via HTTP endpoints.

This API service downloads PDFs from URLs, converts each page to an image, uses OpenAI's Vision API to extract structured HTML that preserves the original layout and formatting, and returns the complete HTML document.

## Features

- **HTTP API**: Simple REST endpoints for PDF to HTML conversion
- **URL-based**: Accepts PDF URLs instead of local files
- **Layout Preservation**: Maintains original document structure and formatting
- **Multi-column Support**: Handles complex layouts with grid and column modes
- **OpenAI Integration**: Uses GPT-4 Vision for accurate text extraction
- **Background Processing**: Efficient handling with automatic cleanup
- **Multiple Output Formats**: JSON response or direct HTML

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd pdf2llm2html
```

2. Install dependencies:
```bash
pip install -e .
```

3. Set up environment variables:
```bash
cp env.example .env
# Edit .env and add your OpenAI API key
```

## Configuration

Create a `.env` file with the following variables:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini
```

## Usage

### Starting the API Server

```bash
# Using uvicorn directly
uvicorn src.pdf2html_api.main:app --host 0.0.0.0 --port 8000

# Or using the package entry point
pdf2html-api
```

The API will be available at `http://localhost:8000`

### API Endpoints

#### 1. Convert PDF to HTML (JSON Response)

**POST** `/convert`

Converts a PDF from URL to HTML and returns a JSON response with metadata.

**Request Body:**
```json
{
  "pdf_url": "https://example.com/document.pdf",
  "model": "gpt-4o-mini",
  "dpi": 200,
  "max_tokens": 4000,
  "temperature": 0.0,
  "css_mode": "grid"
}
```
```

**Response:**
```json
{
  "html": "<!DOCTYPE html>...",
  "pages_processed": 3,
  "model_used": "gpt-4o-mini",
  "css_mode": "grid"
}
```

#### 2. Convert PDF to HTML (Direct HTML Response)

**POST** `/convert/html`

Converts a PDF from URL to HTML and returns the HTML directly.

**Request Body:** Same as above

**Response:** Raw HTML content with `Content-Type: text/html`

#### 3. Health Check

**GET** `/health`

Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "pdf2html-api"
}
```

#### 4. API Information

**GET** `/`

Returns API information and available endpoints.

### Parameters

- **pdf_url** (required): URL of the PDF file to convert
- **model** (optional): OpenAI model to use (default: "gpt-4o-mini")
- **dpi** (optional): Image resolution for PDF rendering (default: 200, range: 72-600)
- **max_tokens** (optional): Maximum tokens for LLM response (default: 4000, range: 100-8000)
- **temperature** (optional): LLM temperature setting (default: 0.0, range: 0.0-2.0)
- **css_mode** (optional): CSS layout mode (default: "grid", options: "grid", "columns", "single")

### CSS Modes

- **grid**: Uses CSS Grid for multi-column layouts
- **columns**: Uses CSS Columns for flowing column layouts
- **single**: Forces single column layout for all content

## Example Usage

### Using curl

```bash
# Convert PDF to HTML with JSON response
curl -X POST "http://localhost:8000/convert" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_url": "https://example.com/document.pdf",
    "css_mode": "grid"
  }'

# Convert PDF to HTML with direct HTML response
curl -X POST "http://localhost:8000/convert/html" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_url": "https://example.com/document.pdf"
  }' \
  -o output.html
```

### Using Python

```python
import httpx

async def convert_pdf():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/convert",
            json={
                "pdf_url": "https://example.com/document.pdf",
                "css_mode": "grid"
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"Converted {result['pages_processed']} pages")
            print(f"HTML: {result['html'][:200]}...")
        else:
            print(f"Error: {response.text}")
```

## API Documentation

Once the server is running, you can access:

- **Interactive API docs**: http://localhost:8000/docs
- **ReDoc documentation**: http://localhost:8000/redoc

## Error Handling

The API returns appropriate HTTP status codes:

- **200**: Successful conversion
- **400**: Bad request (invalid URL, parameters, etc.)
- **500**: Internal server error (conversion failed, API errors, etc.)

Error responses include detailed error messages:

```json
{
  "detail": "Failed to download PDF: HTTP 404"
}
```

## Development

### Running Tests

```bash
pytest tests/
```

### Project Structure

```
src/pdf2html_api/
├── __init__.py
├── main.py              # FastAPI application
├── config.py            # Configuration management
├── html_merge.py        # HTML document assembly
├── llm.py              # OpenAI Vision API integration
├── pdf_to_images.py    # PDF to image conversion
└── prompts/
    └── image_to_html.md # LLM prompt template
```

## Dependencies

- **FastAPI**: Web framework
- **Uvicorn**: ASGI server
- **PyMuPDF**: PDF processing
- **OpenAI**: Vision API integration
- **Pydantic**: Data validation
- **httpx**: HTTP client for downloading PDFs
- **python-dotenv**: Environment variable management

## License

MIT License - see LICENSE file for details. 