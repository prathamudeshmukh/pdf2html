"""OpenAI Vision API integration for converting images to HTML."""

import base64
import re
from pathlib import Path
from typing import Literal, Union

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


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
            # Fallback prompt if file not found
            return """You are an expert document vision model. Convert the provided PAGE IMAGE into clean, semantic HTML that faithfully preserves layout and reading order.

Strict requirements:
- Return ONLY the inner HTML for a single page wrapped in: <section class="page"> ... </section>
- Do NOT include <html>, <head>, or <body>.
- Preserve multi-column layouts. Prefer structured containers over absolute positioning.
- Use semantic tags where appropriate: h1–h6, p, ul/ol/li, table/thead/tbody/tr/th/td, figure/figcaption, header/footer, section/article.
- For columnar content: 
  - If you infer exactly two columns for most of the page, wrap the main content in <div class="columns-2">...</div> (for columns mode) OR <div class="grid-2col">...</div> (for grid mode).
  - Keep reading order top-to-bottom within each column.
- For tables, output proper <table> markup with thead/tbody.
- For text blocks, keep paragraphs in <p>. For small labels/use <span>.
- Include minimal inline styles ONLY when essential (e.g., bold, italic) and avoid absolute coordinates.
- Preserve headings hierarchy according to visual size/weight.
- Include images as <img alt=""> with no src (use data-empty src) if extraction is not available.
- Avoid hallucinating content. If illegible, use: <p class="ocr-uncertain">[illegible]</p>.

Output rules:
- Your response must be valid HTML fragment for ONE page.
- No additional commentary, no JSON, no markdown fences."""
    
    def _encode_image(self, image_path: Path) -> str:
        """
        Encode image to base64 for OpenAI API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Base64 encoded image string
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    
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
        # Encode image
        base64_image = self._encode_image(image_path)
        
        # Prepare the prompt with CSS mode context
        system_prompt = self.prompt_template
        user_prompt = f"""Analyze this page image and convert it to HTML. 

IMPORTANT LAYOUT ANALYSIS:
- Analyze the page in distinct sections (top, middle, bottom, etc.)
- For each section, determine if it has single column or multi-column layout
- Apply appropriate layout containers to each section separately
- Tables should keep their original column structure (don't wrap in multi-column containers)
- Use {css_mode} mode for sections that clearly have multi-column layout
- If css_mode is 'single', force single column layout for all sections

SECTION-BASED APPROACH:
- Top section: Apply appropriate layout (single or multi-column)
- Middle section: Apply appropriate layout (single or multi-column)
- Bottom section: Apply appropriate layout (single or multi-column)
- Tables: Keep original structure, don't force into layout containers

Focus on preserving the exact visual layout and reading order of the original document."""
        
        try:
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
            
            return response.choices[0].message.content
            
        except Exception as e:
            # Log the error for debugging
            print(f"OpenAI API error: {e}")
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
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Call OpenAI Vision API
        raw_response = self._call_openai_vision(image_path, css_mode)
        
        # Clean and validate the response
        cleaned_html = self._clean_html_response(raw_response)
        
        return cleaned_html 