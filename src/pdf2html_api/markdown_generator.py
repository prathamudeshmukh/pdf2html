"""OpenAI Vision API integration for converting page images to Markdown."""

import base64
import logging
import re
import time
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_FALLBACK_PROMPT = (
    "Convert this PDF page image to clean GitHub-Flavored Markdown. "
    "Preserve headings, lists, tables, and emphasis. Return raw Markdown only."
)


class MarkdownGenerator:
    """Generate Markdown from page images using OpenAI Vision API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 4000,
        temperature: float = 0.0,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompts" / "image_to_markdown.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _FALLBACK_PROMPT

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _clean_markdown_response(self, response: str) -> str:
        """Strip accidental wrapper code fences the model may add."""
        response = re.sub(r"^```(?:markdown)?\s*\n?", "", response, flags=re.IGNORECASE)
        response = re.sub(r"\n?```\s*$", "", response, flags=re.IGNORECASE)
        return response.strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def _call_openai_vision(self, image_path: Path) -> str:
        start = time.time()
        logger.info(f"Calling OpenAI Vision API (markdown) with model: {self.model}")

        base64_image = self._encode_image(image_path)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Convert this page image to Markdown. Return raw Markdown only.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                },
                            },
                        ],
                    },
                ],
                max_completion_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            elapsed = time.time() - start
            content = response.choices[0].message.content
            logger.info(f"OpenAI response received in {elapsed:.3f}s ({len(content)} chars)")
            return content
        except Exception as exc:
            logger.error(f"OpenAI API error after {time.time() - start:.3f}s: {exc}")
            raise

    def image_page_to_markdown(self, image_path: Path) -> str:
        """Convert a single page image to Markdown.

        Args:
            image_path: Path to the page PNG image.

        Returns:
            Markdown string for the page.

        Raises:
            FileNotFoundError: If the image file does not exist.
            Exception: If the OpenAI API call fails after retries.
        """
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        raw = self._call_openai_vision(Path(image_path))
        return self._clean_markdown_response(raw)
