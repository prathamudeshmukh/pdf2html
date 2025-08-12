"""Tests for PDF2HTML API endpoints."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from pdf2html_api.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test the root endpoint returns API information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "PDF2HTML API"
    assert data["version"] == "0.1.0"
    assert "convert" in data["endpoints"]


def test_health_endpoint():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pdf2html-api"


def test_convert_endpoint_invalid_url():
    """Test convert endpoint with invalid URL."""
    response = client.post("/convert", json={"pdf_url": "not-a-valid-url"})
    assert response.status_code == 422  # Validation error


def test_convert_endpoint_missing_url():
    """Test convert endpoint with missing URL."""
    response = client.post("/convert", json={})
    assert response.status_code == 422  # Validation error


def test_convert_endpoint_invalid_css_mode():
    """Test convert endpoint with invalid CSS mode."""
    response = client.post(
        "/convert",
        json={"pdf_url": "https://example.com/test.pdf", "css_mode": "invalid_mode"},
    )
    assert response.status_code == 500  # Will fail during processing, not validation


@patch("pdf2html_api.main.get_settings")
@patch("pdf2html_api.main._download_pdf_from_url")
@patch("pdf2html_api.main.render_pdf_to_images")
@patch("pdf2html_api.main.HTMLGenerator")
@patch("pdf2html_api.main.merge_pages")
def test_convert_endpoint_success(
    mock_merge_pages,
    mock_html_generator_class,
    mock_render_pdf,
    mock_download_pdf,
    mock_get_settings,
):
    """Test successful PDF conversion."""
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.openai_api_key = "test-key"
    mock_settings.model = "gpt-4o-mini"
    mock_settings.dpi = 200
    mock_settings.max_tokens = 4000
    mock_settings.temperature = 0.0
    mock_settings.css_mode = "grid"
    mock_get_settings.return_value = mock_settings

    # Mock PDF download
    mock_download_pdf.return_value = "/tmp/test.pdf"

    # Mock PDF to images
    mock_render_pdf.return_value = (["/tmp/page1.png"], MagicMock())

    # Mock HTML generator
    mock_html_generator = MagicMock()
    mock_html_generator.image_page_to_html.return_value = (
        '<section class="page"><p>Test content</p></section>'
    )
    mock_html_generator_class.return_value = mock_html_generator

    # Mock HTML merge
    mock_merge_pages.return_value = (
        "<!DOCTYPE html><html><body><p>Test content</p></body></html>"
    )

    response = client.post(
        "/convert", json={"pdf_url": "https://example.com/test.pdf", "css_mode": "grid"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "html" in data
    assert data["pages_processed"] == 1
    assert data["model_used"] == "gpt-4o-mini"
    assert data["css_mode"] == "grid"


@patch("pdf2html_api.main.get_settings")
@patch("pdf2html_api.main._download_pdf_from_url")
@patch("pdf2html_api.main.render_pdf_to_images")
@patch("pdf2html_api.main.HTMLGenerator")
@patch("pdf2html_api.main.merge_pages")
def test_convert_html_endpoint_success(
    mock_merge_pages,
    mock_html_generator_class,
    mock_render_pdf,
    mock_download_pdf,
    mock_get_settings,
):
    """Test successful PDF conversion with direct HTML response."""
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.openai_api_key = "test-key"
    mock_settings.model = "gpt-4o-mini"
    mock_settings.dpi = 200
    mock_settings.max_tokens = 4000
    mock_settings.temperature = 0.0
    mock_settings.css_mode = "grid"
    mock_get_settings.return_value = mock_settings

    # Mock PDF download
    mock_download_pdf.return_value = "/tmp/test.pdf"

    # Mock PDF to images
    mock_render_pdf.return_value = (["/tmp/page1.png"], MagicMock())

    # Mock HTML generator
    mock_html_generator = MagicMock()
    mock_html_generator.image_page_to_html.return_value = (
        '<section class="page"><p>Test content</p></section>'
    )
    mock_html_generator_class.return_value = mock_html_generator

    # Mock HTML merge
    mock_merge_pages.return_value = (
        "<!DOCTYPE html><html><body><p>Test content</p></body></html>"
    )

    response = client.post(
        "/convert/html",
        json={"pdf_url": "https://example.com/test.pdf", "css_mode": "grid"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in response.text
