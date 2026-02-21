"""
Tests for src/pdf2html_api/services/conversion_pipeline.py

Coverage
--------
- ConversionPipeline._configure_settings  (request → Settings wiring)
"""

from src.pdf2html_api.main import PDFRequest
from src.pdf2html_api.services.conversion_pipeline import ConversionPipeline


class TestConversionPipelineConfiguration:
    def _make_pipeline(self, **request_kwargs):
        pipeline = ConversionPipeline(
            PDFRequest(pdf_url="https://example.com/test.pdf", **request_kwargs)
        )
        return pipeline, pipeline._settings

    def test_model_override(self):
        _, s = self._make_pipeline(model="gpt-4o")
        assert s.model == "gpt-4o"

    def test_dpi_override(self):
        _, s = self._make_pipeline(dpi=300)
        assert s.dpi == 300

    def test_max_tokens_override(self):
        _, s = self._make_pipeline(max_tokens=2000)
        assert s.max_tokens == 2000

    def test_temperature_override(self):
        _, s = self._make_pipeline(temperature=0.7)
        assert s.temperature == 0.7

    def test_max_parallel_workers_override(self):
        _, s = self._make_pipeline(max_parallel_workers=5)
        assert s.max_parallel_workers == 5

    def test_css_mode_columns_accepted(self):
        _, s = self._make_pipeline(css_mode="columns")
        assert s.css_mode == "columns"

    def test_css_mode_single_accepted(self):
        _, s = self._make_pipeline(css_mode="single")
        assert s.css_mode == "single"

    def test_default_css_mode_is_grid(self):
        _, s = self._make_pipeline()
        assert s.css_mode == "grid"
