"""Tests for src/pdf2html_api/services/markdown_pipeline.py"""

from src.pdf2html_api.main import MarkdownRequest
from src.pdf2html_api.services.markdown_pipeline import MarkdownConversionPipeline


class TestMarkdownPipelineConfiguration:
    def _make_pipeline(self, **request_kwargs):
        pipeline = MarkdownConversionPipeline(
            MarkdownRequest(pdf_url="https://example.com/test.pdf", **request_kwargs)
        )
        return pipeline, pipeline._settings

    def test_default_model(self):
        _, s = self._make_pipeline()
        assert s.model == "gpt-4o-mini"

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

    def test_default_dpi(self):
        _, s = self._make_pipeline()
        assert s.dpi == 200
