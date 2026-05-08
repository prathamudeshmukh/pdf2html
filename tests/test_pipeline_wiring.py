"""Integration tests: StructuralExtractor + ImageInjector wired into ConversionPipeline."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.pdf2html_api.main import PDFRequest
from src.pdf2html_api.services.conversion_pipeline import ConversionPipeline
from src.pdf2html_api.services.structural_extractor import PageMetadata, ExtractedImage


def _make_request(**kwargs):
    return PDFRequest(pdf_url="https://example.com/test.pdf", **kwargs)


def _make_page_metadata(page_index=0):
    return PageMetadata(
        page_index=page_index,
        colored_regions=[{"bbox": (0, 0, 100, 30), "fill": "#1a237e", "stroke": None}],
        text_colors=["#ffffff"],
        images=[
            ExtractedImage(
                id="img_0",
                bbox=(0, 0, 50, 50),
                data_url="data:image/png;base64,AAAA",
                width=50,
                height=50,
            )
        ],
    )


def _fake_pdf_path():
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(b"%PDF stub")
    tmp.close()
    return Path(tmp.name)


def _run(coro):
    return asyncio.run(coro)


class TestPipelineStructuralExtractorWiring:
    """StructuralExtractor.extract_all is called after render_pdf_to_images."""

    def _make_patched_pipeline(self, metadata_list=None, raise_in_extractor=False):
        pdf_path = _fake_pdf_path()
        image_path = Path("/tmp/page_001.png")
        temp_dir = MagicMock()
        page_html = '<section class="page"><p>Hello</p></section>'

        patches = {
            "downloader": patch.object(
                ConversionPipeline, "_downloader",
                new_callable=lambda: property(lambda self: self.__dict__.setdefault("_dl", MagicMock())),
            ),
        }

        pipeline = ConversionPipeline(_make_request())

        pipeline._downloader = MagicMock()
        pipeline._downloader.download = AsyncMock(return_value=pdf_path)

        pipeline._page_processor = MagicMock()
        pipeline._page_processor.process_pages = AsyncMock(return_value=[page_html])

        return pipeline, pdf_path, image_path, temp_dir, page_html

    def test_structural_extractor_called_with_pdf_path(self):
        pipeline, pdf_path, image_path, temp_dir, _ = self._make_patched_pipeline()

        with (
            patch("src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
                  return_value=([image_path], temp_dir)),
            patch("src.pdf2html_api.services.conversion_pipeline.StructuralExtractor") as mock_extractor,
            patch("src.pdf2html_api.services.conversion_pipeline.ImageInjector"),
        ):
            mock_extractor.extract_all.return_value = [_make_page_metadata()]
            _run(pipeline.execute("req_test"))

        mock_extractor.extract_all.assert_called_once_with(pdf_path)

    def test_structural_extractor_failure_does_not_abort_pipeline(self):
        pipeline, pdf_path, image_path, temp_dir, page_html = self._make_patched_pipeline()

        with (
            patch("src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
                  return_value=([image_path], temp_dir)),
            patch("src.pdf2html_api.services.conversion_pipeline.StructuralExtractor") as mock_extractor,
            patch("src.pdf2html_api.services.conversion_pipeline.ImageInjector") as mock_injector,
        ):
            mock_extractor.extract_all.side_effect = Exception("fitz crashed")
            mock_injector.inject_all.return_value = [page_html]
            result = _run(pipeline.execute("req_test"))

        # Pipeline should complete and return HTML despite extractor failure
        assert result.html is not None
        assert result.pages_processed == 1

    def test_page_metadata_passed_to_page_processor(self):
        pipeline, pdf_path, image_path, temp_dir, _ = self._make_patched_pipeline()
        meta = [_make_page_metadata()]

        with (
            patch("src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
                  return_value=([image_path], temp_dir)),
            patch("src.pdf2html_api.services.conversion_pipeline.StructuralExtractor") as mock_extractor,
            patch("src.pdf2html_api.services.conversion_pipeline.ImageInjector"),
        ):
            mock_extractor.extract_all.return_value = meta
            _run(pipeline.execute("req_test"))

        call_kwargs = pipeline._page_processor.process_pages.call_args.kwargs
        assert call_kwargs.get("page_metadata") == meta


class TestPipelineImageInjectorWiring:
    """ImageInjector.inject_all is called after page processing."""

    def _build_pipeline(self):
        pdf_path = _fake_pdf_path()
        image_path = Path("/tmp/page_001.png")
        temp_dir = MagicMock()
        page_html = '<section class="page"><img data-img-ref="img_0"></section>'

        pipeline = ConversionPipeline(_make_request())
        pipeline._downloader = MagicMock()
        pipeline._downloader.download = AsyncMock(return_value=pdf_path)
        pipeline._page_processor = MagicMock()
        pipeline._page_processor.process_pages = AsyncMock(return_value=[page_html])
        return pipeline, pdf_path, image_path, temp_dir, page_html

    def test_image_injector_called_with_page_html_and_metadata(self):
        pipeline, pdf_path, image_path, temp_dir, page_html = self._build_pipeline()
        meta = [_make_page_metadata()]

        with (
            patch("src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
                  return_value=([image_path], temp_dir)),
            patch("src.pdf2html_api.services.conversion_pipeline.StructuralExtractor") as mock_extractor,
            patch("src.pdf2html_api.services.conversion_pipeline.ImageInjector") as mock_injector,
        ):
            mock_extractor.extract_all.return_value = meta
            mock_injector.inject_all.return_value = [page_html]
            _run(pipeline.execute("req_test"))

        mock_injector.inject_all.assert_called_once_with([page_html], meta)

    def test_image_injector_failure_does_not_abort_pipeline(self):
        pipeline, pdf_path, image_path, temp_dir, page_html = self._build_pipeline()

        with (
            patch("src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
                  return_value=([image_path], temp_dir)),
            patch("src.pdf2html_api.services.conversion_pipeline.StructuralExtractor") as mock_extractor,
            patch("src.pdf2html_api.services.conversion_pipeline.ImageInjector") as mock_injector,
        ):
            mock_extractor.extract_all.return_value = []
            mock_injector.inject_all.side_effect = Exception("injector crashed")
            result = _run(pipeline.execute("req_test"))

        assert result.html is not None
        assert result.pages_processed == 1

    def test_pdf_response_shape_unchanged(self):
        pipeline, pdf_path, image_path, temp_dir, _ = self._build_pipeline()

        with (
            patch("src.pdf2html_api.services.conversion_pipeline.render_pdf_to_images",
                  return_value=([image_path], temp_dir)),
            patch("src.pdf2html_api.services.conversion_pipeline.StructuralExtractor") as mock_extractor,
            patch("src.pdf2html_api.services.conversion_pipeline.ImageInjector") as mock_injector,
        ):
            mock_extractor.extract_all.return_value = []
            mock_injector.inject_all.return_value = ['<section class="page">ok</section>']
            result = _run(pipeline.execute("req_test"))

        assert hasattr(result, "html")
        assert hasattr(result, "pages_processed")
        assert hasattr(result, "model_used")
        assert hasattr(result, "css_mode")
        assert hasattr(result, "sample_json")
