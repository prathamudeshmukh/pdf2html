"""Replace data-img-ref placeholders in LLM-generated HTML with base64 data URLs."""

import logging

from bs4 import BeautifulSoup

from pdf2html_api.services.structural_extractor import ExtractedImage, PageMetadata

logger = logging.getLogger(__name__)


class ImageInjector:
    @staticmethod
    def inject(html: str, images: list[ExtractedImage]) -> str:
        """Replace every <img data-img-ref="img_N"> with the matching base64 src.

        Unmatched refs get src="". Original HTML is returned unchanged if no
        data-img-ref attributes are present.
        """
        if "data-img-ref" not in html:
            return html

        image_map = {img.id: img.data_url for img in images}

        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("img", attrs={"data-img-ref": True}):
            ref = tag["data-img-ref"]
            tag["src"] = image_map.get(ref, "")
            del tag["data-img-ref"]

        # lxml wraps output in <html><body> — extract just the inner content
        body = soup.find("body")
        if body is not None:
            return "".join(str(child) for child in body.children)
        return str(soup)

    @staticmethod
    def inject_all(
        page_html_list: list[str],
        page_metadata_list: list[PageMetadata],
    ) -> list[str]:
        """Apply inject() to each page using its corresponding PageMetadata.

        Pages without a matching metadata entry are returned unchanged.
        Any per-page failure is caught and the original HTML is returned for that page.
        """
        result: list[str] = []
        for i, html in enumerate(page_html_list):
            try:
                if i < len(page_metadata_list):
                    html = ImageInjector.inject(html, page_metadata_list[i].images)
            except Exception as exc:
                logger.warning("ImageInjector failed for page %d: %s", i, exc)
            result.append(html)
        return result
