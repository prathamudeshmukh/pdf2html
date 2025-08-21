"""OpenAI Vision API integration for converting images to HTML."""

import base64
import re
import time
import logging
from pathlib import Path
from typing import Literal, Union

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class HTMLGenerator:
    """Generate HTML from images using OpenAI Vision API."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 4000,
        temperature: float = 0.0,
    ):
        """
        Initialize the HTML generator.
        
        Args:
            api_key: OpenAI API key
            model: OpenAI model to use
            max_tokens: Maximum tokens for response
            temperature: Temperature setting for generation
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Load the prompt template
        self.prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        """Load the prompt template from the markdown file."""
        prompt_path = Path(__file__).parent / "prompts" / "image_to_html.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # Optimized fallback prompt for faster processing
            return """Convert this image to HTML. Use semantic tags (h1-h6, p, table, ul/ol). For multi-column layouts, use <div class="grid-2col"> or <div class="columns-2">. Return only HTML wrapped in <section class="page">...</section>. No explanations."""
    
    def _encode_image(self, image_path: Path) -> str:
        """
        Encode image to base64 for OpenAI API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Base64 encoded image string
        """
        encode_start = time.time()
        logger.info(f"Encoding image to base64: {image_path}")
        
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            encoded = base64.b64encode(image_data).decode("utf-8")
            
        encode_time = time.time() - encode_start
        logger.info(f"Image encoded in {encode_time:.3f}s, size: {len(image_data)} bytes -> {len(encoded)} chars")
        
        return encoded
    
    def _clean_html_response(self, response: str) -> str:
        """
        Clean and validate the HTML response from the LLM.
        
        Args:
            response: Raw response from OpenAI
            
        Returns:
            Cleaned HTML string
        """
        # Remove markdown code fences if present
        response = re.sub(r"^```html?\s*", "", response, flags=re.IGNORECASE)
        response = re.sub(r"```\s*$", "", response, flags=re.IGNORECASE)
        
        # Remove leading/trailing whitespace
        response = response.strip()
        
        # Ensure response is wrapped in section.page
        if not response.startswith("<section class=\"page\">"):
            if response.startswith("<section"):
                # Fix class attribute if missing
                response = re.sub(r"<section([^>]*)>", r'<section\1 class="page">', response, count=1)
            else:
                # Wrap in section if not present
                response = f'<section class="page">{response}</section>'
        
        if not response.endswith("</section>"):
            response = f"{response}</section>"
        
        return response
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    def _call_openai_vision(self, image_path: Path, css_mode: Literal["grid", "columns", "single"]) -> str:
        """
        Call OpenAI Vision API with retry logic.
        
        Args:
            image_path: Path to the image file
            css_mode: CSS mode for column layout hints
            
        Returns:
            HTML response from OpenAI
            
        Raises:
            Exception: If API call fails after retries
        """
        api_start = time.time()
        logger.info(f"Calling OpenAI Vision API with model: {self.model}")
        
        # Encode image
        base64_image = self._encode_image(image_path)
        
        # Prepare the prompt with CSS mode context
        prompt_start = time.time()
        system_prompt = self.prompt_template
        user_prompt = f"Convert this image to HTML using {css_mode} layout. Preserve original structure and reading order."
        
        prompt_time = time.time() - prompt_start
        logger.info(f"Prompt prepared in {prompt_time:.3f}s, CSS mode: {css_mode}")
        
        try:
            logger.info("Making OpenAI API request...")
            api_request_start = time.time()
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt,
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
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            
            api_request_time = time.time() - api_request_start
            api_total_time = time.time() - api_start
            
            response_content = response.choices[0].message.content
            logger.info(f"OpenAI API response received in {api_request_time:.3f}s")
            logger.info(f"Response length: {len(response_content)} chars")
            logger.info(f"Total API call time: {api_total_time:.3f}s")
            
            # Log usage if available
            if hasattr(response, 'usage') and response.usage:
                logger.info(f"Token usage - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}, Total: {response.usage.total_tokens}")
            
            return response_content
            
        except Exception as e:
            api_time = time.time() - api_start
            logger.error(f"OpenAI API error after {api_time:.3f}s: {e}")
            raise
    
    def image_page_to_html(
        self, image_path: Path, css_mode: Literal["grid", "columns", "single"]
    ) -> str:
        """
        Convert a single page image to HTML.
        
        Args:
            image_path: Path to the page image
            css_mode: CSS mode for column layout hints
            
        Returns:
            HTML string for the page
            
        Raises:
            FileNotFoundError: If image file doesn't exist
            Exception: If OpenAI API call fails
        """
        page_start = time.time()
        logger.info(f"Starting image to HTML conversion: {image_path}")
        
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Call OpenAI Vision API
        api_start = time.time()
        raw_response = self._call_openai_vision(image_path, css_mode)
        api_time = time.time() - api_start
        
        # Clean and validate the response
        cleanup_start = time.time()
        cleaned_html = self._clean_html_response(raw_response)
        cleanup_time = time.time() - cleanup_start
        
        total_time = time.time() - page_start
        logger.info(f"Image to HTML conversion completed in {total_time:.3f}s")
        logger.info(f"  - API call: {api_time:.3f}s ({api_time/total_time*100:.1f}%)")
        logger.info(f"  - HTML cleanup: {cleanup_time:.3f}s ({cleanup_time/total_time*100:.1f}%)")
        logger.info(f"  - Final HTML length: {len(cleaned_html)} chars")
        
        return cleaned_html 