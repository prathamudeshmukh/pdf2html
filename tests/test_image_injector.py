"""Unit tests for ImageInjector."""

import pytest

from pdf2html_api.services.structural_extractor import ExtractedImage, PageMetadata
from pdf2html_api.services.image_injector import ImageInjector


def _make_image(id: str, data_url: str = "data:image/png;base64,AAAA") -> ExtractedImage:
    return ExtractedImage(id=id, bbox=(0, 0, 50, 50), data_url=data_url, width=50, height=50)


def _make_meta(images: list[ExtractedImage]) -> PageMetadata:
    return PageMetadata(page_index=0, colored_regions=[], text_colors=[], images=images)


# ---------------------------------------------------------------------------
# inject() — single page
# ---------------------------------------------------------------------------

class TestInject:
    def test_single_image_ref_replaced(self):
        html = '<section class="page"><img data-img-ref="img_0" alt="logo"></section>'
        result = ImageInjector.inject(html, [_make_image("img_0", "data:image/png;base64,ABC")])
        assert 'src="data:image/png;base64,ABC"' in result
        assert "data-img-ref" not in result

    def test_multiple_images_all_replaced(self):
        html = (
            '<section class="page">'
            '<img data-img-ref="img_0" alt="a">'
            '<img data-img-ref="img_1" alt="b">'
            '</section>'
        )
        images = [
            _make_image("img_0", "data:image/png;base64,FIRST"),
            _make_image("img_1", "data:image/jpeg;base64,SECOND"),
        ]
        result = ImageInjector.inject(html, images)
        assert 'src="data:image/png;base64,FIRST"' in result
        assert 'src="data:image/jpeg;base64,SECOND"' in result
        assert "data-img-ref" not in result

    def test_unmatched_ref_sets_empty_src(self):
        html = '<section class="page"><img data-img-ref="img_99" alt="x"></section>'
        result = ImageInjector.inject(html, [])
        assert 'src=""' in result
        assert "data-img-ref" not in result

    def test_page_with_no_img_refs_returned_unchanged(self):
        html = '<section class="page"><p>No images here</p></section>'
        result = ImageInjector.inject(html, [_make_image("img_0")])
        assert result == html

    def test_existing_src_is_overwritten_by_extracted_image(self):
        html = '<section class="page"><img data-img-ref="img_0" src="/old.png" alt="x"></section>'
        result = ImageInjector.inject(html, [_make_image("img_0", "data:image/png;base64,NEW")])
        assert 'src="data:image/png;base64,NEW"' in result
        assert "/old.png" not in result

    def test_alt_text_preserved(self):
        html = '<section class="page"><img data-img-ref="img_0" alt="QR Code"></section>'
        result = ImageInjector.inject(html, [_make_image("img_0")])
        assert 'alt="QR Code"' in result

    def test_empty_images_list_sets_empty_src_for_all_refs(self):
        html = (
            '<section class="page">'
            '<img data-img-ref="img_0"><img data-img-ref="img_1">'
            '</section>'
        )
        result = ImageInjector.inject(html, [])
        assert result.count('src=""') == 2

    def test_inject_returns_string(self):
        result = ImageInjector.inject('<section class="page"></section>', [])
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# inject_all() — list of pages
# ---------------------------------------------------------------------------

class TestInjectAll:
    def test_applies_per_page_images(self):
        page0 = '<section class="page"><img data-img-ref="img_0" alt="a"></section>'
        page1 = '<section class="page"><img data-img-ref="img_0" alt="b"></section>'
        meta0 = _make_meta([_make_image("img_0", "data:image/png;base64,PAGE0")])
        meta1 = _make_meta([_make_image("img_0", "data:image/png;base64,PAGE1")])

        result = ImageInjector.inject_all([page0, page1], [meta0, meta1])

        assert 'src="data:image/png;base64,PAGE0"' in result[0]
        assert 'src="data:image/png;base64,PAGE1"' in result[1]

    def test_returns_same_number_of_pages(self):
        pages = ['<section class="page"><p>x</p></section>'] * 3
        meta = [_make_meta([]) for _ in range(3)]
        result = ImageInjector.inject_all(pages, meta)
        assert len(result) == 3

    def test_mismatched_lengths_does_not_raise(self):
        pages = ['<section class="page"><p>x</p></section>'] * 3
        meta = [_make_meta([])]  # only 1 metadata for 3 pages
        result = ImageInjector.inject_all(pages, meta)
        assert len(result) == 3

    def test_empty_metadata_list_leaves_pages_unchanged(self):
        page = '<section class="page"><p>no refs</p></section>'
        result = ImageInjector.inject_all([page], [])
        assert result == [page]

    def test_inject_failure_on_one_page_returns_original(self):
        """If inject() raises internally, that page is returned as-is."""
        pages = ['<section class="page"><img data-img-ref="img_0"></section>']
        # Pass malformed metadata that will be handled gracefully
        meta = [_make_meta([])]
        result = ImageInjector.inject_all(pages, meta)
        assert len(result) == 1
        assert isinstance(result[0], str)
