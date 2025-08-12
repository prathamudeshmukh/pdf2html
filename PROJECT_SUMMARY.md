# PDF2HTML API - Project Summary

## Overview

PDF2HTML API is a FastAPI-based web service that converts PDF documents to HTML using OpenAI's Vision API. The service accepts PDF URLs, processes each page through AI vision analysis, and returns structured HTML that preserves the original document layout and formatting.

## Architecture

### Core Components

1. **FastAPI Application** (`src/pdf2html_api/main.py`)
   - RESTful API endpoints for PDF conversion
   - Request/response models with Pydantic validation
   - Background task management for cleanup
   - Error handling and HTTP status codes

2. **Configuration Management** (`src/pdf2html_api/config.py`)
   - Environment variable support
   - OpenAI API key management
   - Parameter validation and defaults
   - Settings class with Pydantic models

3. **PDF Processing** (`src/pdf2html_api/pdf_to_images.py`)
   - PyMuPDF integration for PDF rendering
   - Page-by-page image conversion
   - Temporary file management
   - DPI and quality control

4. **AI Integration** (`src/pdf2html_api/llm.py`)
   - OpenAI Vision API client
   - Retry logic with exponential backoff
   - HTML response cleaning and validation
   - Prompt template management

5. **HTML Assembly** (`src/pdf2html_api/html_merge.py`)
   - Multi-page HTML document creation
   - CSS generation for different layout modes
   - Responsive design support
   - Print-friendly styling

6. **Prompt Engineering** (`src/pdf2html_api/prompts/`)
   - Specialized prompts for layout analysis
   - Multi-column detection instructions
   - Section-based layout preservation
   - HTML structure guidelines

### API Endpoints

- **POST /convert**: Convert PDF to HTML with JSON response
- **POST /convert/html**: Convert PDF to HTML with direct HTML response
- **GET /health**: Health check endpoint
- **GET /**: API information and documentation links

### Key Features

- **URL-based Processing**: Accepts PDF URLs instead of file uploads
- **Layout Preservation**: Maintains original document structure
- **Multi-column Support**: Handles complex layouts with grid/column modes
- **Background Processing**: Efficient handling with automatic cleanup
- **Error Resilience**: Graceful error handling and recovery
- **API Documentation**: Auto-generated OpenAPI/Swagger docs

## Technology Stack

- **FastAPI**: Modern web framework for APIs
- **Uvicorn**: ASGI server for production deployment
- **PyMuPDF**: High-performance PDF processing
- **OpenAI**: Vision API for AI-powered conversion
- **Pydantic**: Data validation and serialization
- **httpx**: Async HTTP client for PDF downloads
- **python-dotenv**: Environment configuration

## Development Workflow

1. **Setup**: Install dependencies and configure environment
2. **Development**: Use `python run_api.py` for local development
3. **Testing**: Run `pytest tests/` for unit tests
4. **Documentation**: Access `/docs` for interactive API docs

## Deployment Considerations

- **Environment Variables**: Configure OpenAI API key and server settings
- **Dependencies**: Ensure all system libraries for PyMuPDF are installed
- **Resource Management**: Monitor memory usage for large PDFs
- **Rate Limiting**: Consider OpenAI API rate limits
- **Error Handling**: Implement proper logging and monitoring

## Future Enhancements

- **Caching**: Implement result caching for repeated requests
- **Batch Processing**: Support for multiple PDFs in single request
- **Authentication**: Add API key authentication
- **Rate Limiting**: Implement request rate limiting
- **Monitoring**: Add metrics and health monitoring
- **Docker Support**: Containerized deployment 