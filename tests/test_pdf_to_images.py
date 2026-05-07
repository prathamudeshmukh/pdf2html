"""Tests for PDF-to-image rendering defaults."""

import inspect
from pdf2html_api.pdf_to_images import render_pdf_to_images, _optimize_image_for_api


def test_render_pdf_to_images_default_dpi_is_300():
    sig = inspect.signature(render_pdf_to_images)
    assert sig.parameters["dpi"].default == 300


def test_optimize_image_default_max_size_is_2048():
    sig = inspect.signature(_optimize_image_for_api)
    assert sig.parameters["max_size"].default == 2048
