"""
Characterization tests for the extract_variables feature in ConversionPipeline.

Coverage
--------
- extract_variables=False (default)
  - SampleJSONExtractor is never instantiated
  - apply_sample_json_to_html is never called
  - result.html is the raw merged HTML
  - result.sample_json is None

- extract_variables=True, extraction succeeds
  - SampleJSONExtractor is instantiated with the correct settings values
  - SampleJSONExtractor.extract receives the merged HTML
  - apply_sample_json_to_html receives the merged HTML and the extracted dict
  - result.html is the variable-substituted HTML
  - result.sample_json equals the extracted dict

- extract_variables=True, extraction raises
  - Pipeline does NOT raise – conversion succeeds
  - result.html falls back to the raw merged HTML
  - result.sample_json is None

- extract_variables=True, apply_sample_json_to_html returns falsy string
  - result.html falls back to the raw merged HTML

- result.pages_processed / model_used / css_mode are unaffected by the flag
"""

import asyncio
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.pdf2html_api.main import PDFRequest
from src.pdf2html_api.services.conversion_pipeline import ConversionPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_URL = "https://example.com/test.pdf"
_MERGED_HTML = "<html><body><p>John Smith</p><p>Acme Corp</p></body></html>"
_VARIABLES_HTML = "<html><body><p>{{name}}</p><p>{{company}}</p></body></html>"
_SAMPLE_JSON = {"name": "John Smith", "company": "Acme Corp"}

_PAGE_HTML_LIST = ['<section class="page"><p>John Smith</p></section>']


def _make_pdf_path() -> Path:
    """Create a real temp file so stat() calls inside the pipeline don't fail."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(b"%PDF stub")
    tmp.close()
    return Path(tmp.name)


@contextmanager
def _patch_pipeline_infrastructure(
    *,
    page_html_list=None,
    merged_html=_MERGED_HTML,
):
    """
    Patches all external collaborators of execute() except the
    SampleJSON* layer, returning a dict of the mocks so tests can
    inspect calls.
    """
    page_html_list = page_html_list or _PAGE_HTML_LIST
    pdf_path = _make_pdf_path()
    image_paths = [MagicMock()]
    temp_dir = MagicMock()

    mock_downloader = AsyncMock(return_value=pdf_path)
    mock_render = MagicMock(return_value=(image_paths, temp_dir))
    mock_html_gen = MagicMock()
    mock_process_pages = AsyncMock(return_value=page_html_list)
    mock_merge = MagicMock(return_value=merged_html)
    mock_html_gen_factory = MagicMock()
    mock_html_gen_factory.build.return_value = mock_html_gen
    mock_css_validator = MagicMock()

    with (
        patch(
            "src.pdf2html_api.services.conversion_pipeline.PDFDownloader",
            return_value=MagicMock(download=mock_downloader),
        ),
        patch(
            "src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
            mock_render,
        ),
        patch(
            "src.pdf2html_api.services.conversion_pipeline.HTMLGeneratorFactory",
            mock_html_gen_factory,
        ),
        patch(
            "src.pdf2html_api.services.conversion_pipeline.PageProcessor",
            return_value=MagicMock(process_pages=mock_process_pages),
        ),
        patch(
            "src.pdf2html_api.services.conversion_pipeline.merge_pages",
            mock_merge,
        ),
        patch(
            "src.pdf2html_api.services.conversion_pipeline.CSSModeValidator",
            mock_css_validator,
        ),
    ):
        yield {
            "downloader": mock_downloader,
            "render": mock_render,
            "page_processor": mock_process_pages,
            "merge": mock_merge,
        }


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# extract_variables=False  (default behaviour, unchanged by the new feature)
# ---------------------------------------------------------------------------


class TestExtractVariablesDisabled:
    """When extract_variables is False (or omitted), the JSON extraction layer
    must be a no-op."""

    def _execute(self, **kwargs):
        req = PDFRequest(pdf_url=_BASE_URL, **kwargs)
        pipeline = ConversionPipeline(req)
        return pipeline

    def test_default_flag_is_false(self):
        req = PDFRequest(pdf_url=_BASE_URL)
        assert req.extract_variables is False

    def test_result_html_is_raw_merged_html(self):
        with (
            _patch_pipeline_infrastructure() as _mocks,
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor"
            ) as mock_extractor_cls,
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
            ) as mock_apply,
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-001"))

        assert result.html == _MERGED_HTML

    def test_result_sample_json_is_none(self):
        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor"
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
            ),
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-002"))

        assert result.sample_json is None

    def test_extractor_never_instantiated(self):
        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor"
            ) as mock_extractor_cls,
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
            ),
        ):
            pipeline = self._execute()
            _run(pipeline.execute("req-003"))

        mock_extractor_cls.assert_not_called()

    def test_apply_sample_json_never_called(self):
        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor"
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
            ) as mock_apply,
        ):
            pipeline = self._execute()
            _run(pipeline.execute("req-004"))

        mock_apply.assert_not_called()

    def test_pages_processed_correct(self):
        page_htmls = [
            '<section class="page">P1</section>',
            '<section class="page">P2</section>',
        ]
        with (
            _patch_pipeline_infrastructure(page_html_list=page_htmls),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor"
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
            ),
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-005"))

        assert result.pages_processed == 2


# ---------------------------------------------------------------------------
# extract_variables=True  –  happy path
# ---------------------------------------------------------------------------


class TestExtractVariablesEnabled:
    """When extract_variables=True and extraction succeeds, the pipeline must
    return variable-substituted HTML and the extracted dict."""

    def _execute(self, **kwargs):
        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True, **kwargs)
        pipeline = ConversionPipeline(req)
        return pipeline

    def test_result_html_is_variables_html(self):
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value=_VARIABLES_HTML,
            ),
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-010"))

        assert result.html == _VARIABLES_HTML

    def test_result_sample_json_equals_extracted_dict(self):
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value=_VARIABLES_HTML,
            ),
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-011"))

        assert result.sample_json == _SAMPLE_JSON

    def test_extractor_receives_merged_html(self):
        """extract() must be called with the HTML produced by merge_pages."""
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        with (
            _patch_pipeline_infrastructure(merged_html=_MERGED_HTML),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value=_VARIABLES_HTML,
            ),
        ):
            pipeline = self._execute()
            _run(pipeline.execute("req-012"))

        mock_extractor_instance.extract.assert_called_once_with(_MERGED_HTML)

    def test_apply_receives_merged_html_and_sample_json(self):
        """apply_sample_json_to_html must receive the merged HTML and extracted dict."""
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        with (
            _patch_pipeline_infrastructure(merged_html=_MERGED_HTML),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value=_VARIABLES_HTML,
            ) as mock_apply,
        ):
            pipeline = self._execute()
            _run(pipeline.execute("req-013"))

        mock_apply.assert_called_once_with(_MERGED_HTML, _SAMPLE_JSON)

    def test_extractor_instantiated_with_settings_values(self):
        """SampleJSONExtractor must be constructed with values from Settings."""
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = {}

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ) as MockExtractorCls,
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value="<html></html>",
            ),
        ):
            pipeline = self._execute(model="gpt-4o", max_tokens=1500, temperature=0.3)
            settings = pipeline._settings
            _run(pipeline.execute("req-014"))

        MockExtractorCls.assert_called_once_with(
            api_key=settings.openai_api_key,
            model=settings.model,
            temperature=0.0,
            max_tokens=2000,
        )

    def test_pages_processed_unaffected(self):
        page_htmls = ['<section class="page">P1</section>'] * 3
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        with (
            _patch_pipeline_infrastructure(page_html_list=page_htmls),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value=_VARIABLES_HTML,
            ),
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-015"))

        assert result.pages_processed == 3

    def test_model_used_unaffected(self):
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = {}

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value="<html></html>",
            ),
        ):
            pipeline = self._execute(model="gpt-4o")
            result = _run(pipeline.execute("req-016"))

        assert result.model_used == "gpt-4o"

    def test_css_mode_unaffected(self):
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = {}

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value="<html></html>",
            ),
        ):
            pipeline = self._execute(css_mode="columns")
            result = _run(pipeline.execute("req-017"))

        assert result.css_mode == "columns"

    def test_empty_sample_json_still_calls_apply(self):
        """An empty dict from the extractor is still forwarded to apply."""
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = {}

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value="<html></html>",
            ) as mock_apply,
        ):
            pipeline = self._execute()
            result = _run(pipeline.execute("req-018"))

        mock_apply.assert_called_once()
        assert result.sample_json == {}


# ---------------------------------------------------------------------------
# extract_variables=True  –  extraction failure / graceful degradation
# ---------------------------------------------------------------------------


class TestExtractVariablesErrorHandling:
    """Errors in the SampleJSON layer must NOT propagate – the pipeline should
    complete successfully, using the raw merged HTML and sample_json=None."""

    def _execute(self, exc, **kwargs):
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.side_effect = exc

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True, **kwargs)

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
            ) as mock_apply,
        ):
            pipeline = ConversionPipeline(req)
            result = _run(pipeline.execute("req-err"))

        return result, mock_apply

    def test_does_not_raise_on_value_error(self):
        result, _ = self._execute(ValueError("LLM returned invalid JSON"))
        assert result is not None

    def test_does_not_raise_on_runtime_error(self):
        result, _ = self._execute(RuntimeError("OpenAI timeout"))
        assert result is not None

    def test_does_not_raise_on_generic_exception(self):
        result, _ = self._execute(Exception("unexpected"))
        assert result is not None

    def test_html_falls_back_to_merged_html_on_error(self):
        result, _ = self._execute(ValueError("LLM returned invalid JSON"))
        assert result.html == _MERGED_HTML

    def test_sample_json_is_none_on_error(self):
        result, _ = self._execute(RuntimeError("network error"))
        assert result.sample_json is None

    def test_apply_not_called_when_extract_raises(self):
        _, mock_apply = self._execute(ValueError("bad json"))
        mock_apply.assert_not_called()

    def test_error_is_logged(self, caplog):
        import logging

        mock_extractor_instance = MagicMock()
        error_msg = "LLM returned invalid JSON"
        mock_extractor_instance.extract.side_effect = ValueError(error_msg)

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True)

        with caplog.at_level(logging.ERROR):
            with (
                _patch_pipeline_infrastructure(),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                    return_value=mock_extractor_instance,
                ),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html"
                ),
            ):
                pipeline = ConversionPipeline(req)
                _run(pipeline.execute("req-log"))

        assert any("Variable extraction failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# extract_variables=True  –  falsy html_with_variables fallback
# ---------------------------------------------------------------------------


class TestExtractVariablesFalsyHTMLFallback:
    """If apply_sample_json_to_html returns a falsy value (e.g. empty string),
    the pipeline must fall back to the raw merged HTML."""

    def test_empty_string_from_apply_falls_back_to_merged_html(self):
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True)

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value="",
            ),
        ):
            pipeline = ConversionPipeline(req)
            result = _run(pipeline.execute("req-falsy"))

        assert result.html == _MERGED_HTML

    def test_sample_json_still_populated_when_apply_returns_falsy(self):
        """sample_json reflects what the extractor returned, regardless of apply output."""
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True)

        with (
            _patch_pipeline_infrastructure(),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                return_value="",
            ),
        ):
            pipeline = ConversionPipeline(req)
            result = _run(pipeline.execute("req-falsy-2"))

        assert result.sample_json == _SAMPLE_JSON


# ---------------------------------------------------------------------------
# Logging behaviour
# ---------------------------------------------------------------------------


class TestExtractVariablesLogging:
    """Info-level log lines must be emitted at key stages of extraction."""

    def test_extraction_start_logged(self, caplog):
        import logging

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True)

        with caplog.at_level(logging.INFO):
            with (
                _patch_pipeline_infrastructure(),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                    return_value=mock_extractor_instance,
                ),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                    return_value=_VARIABLES_HTML,
                ),
            ):
                pipeline = ConversionPipeline(req)
                _run(pipeline.execute("req-log-start"))

        messages = [r.message for r in caplog.records]
        assert any("Extracting template variables" in m for m in messages)

    def test_extraction_completion_logged(self, caplog):
        import logging

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = _SAMPLE_JSON

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True)

        with caplog.at_level(logging.INFO):
            with (
                _patch_pipeline_infrastructure(),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                    return_value=mock_extractor_instance,
                ),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                    return_value=_VARIABLES_HTML,
                ),
            ):
                pipeline = ConversionPipeline(req)
                _run(pipeline.execute("req-log-done"))

        messages = [r.message for r in caplog.records]
        assert any("Variable detection completed" in m for m in messages)

    def test_variable_count_appears_in_completion_log(self, caplog):
        import logging

        sample = {"a": "1", "b": "2", "c": "3"}
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = sample

        req = PDFRequest(pdf_url=_BASE_URL, extract_variables=True)

        with caplog.at_level(logging.INFO):
            with (
                _patch_pipeline_infrastructure(),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.SampleJSONExtractor",
                    return_value=mock_extractor_instance,
                ),
                patch(
                    "src.pdf2html_api.services.conversion_pipeline.apply_sample_json_to_html",
                    return_value=_VARIABLES_HTML,
                ),
            ):
                pipeline = ConversionPipeline(req)
                _run(pipeline.execute("req-log-count"))

        messages = [r.message for r in caplog.records]
        assert any("3" in m and "variable" in m.lower() for m in messages)
