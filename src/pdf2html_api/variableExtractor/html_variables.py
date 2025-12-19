import logging
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)


class HTMLVariableExtractor:
    """
    Replaces dynamic values in HTML with Handlebars-style variables.
    Returns HTML only (no JSON).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        prompt_path = (
            Path(__file__).resolve().parent.parent
            / "prompts"
            / "html_variables.md"
        )

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")

        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def extract(self, html: str) -> str:
        """
        Takes raw HTML and returns HTML with {{variables}} replaced.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": html,
                },
            ],
        )

        content = response.choices[0].message.content.strip()

        self._validate_html_output(content)

        return content

    def _validate_html_output(self, html: str):
        """
        Basic safety checks.
        We intentionally keep this light.
        """
        if not html:
            raise ValueError("LLM returned empty output")

        if "<html" in html.lower() or "<body" in html.lower():
            # allowed, but we still log
            logger.debug("HTML output contains full document structure")

        # Guardrail: ensure model did not return JSON accidentally
        if html.lstrip().startswith("{"):
            logger.error("LLM returned JSON but HTML was expected")
            raise ValueError("LLM returned JSON instead of HTML")

        # Optional: ensure at least one variable was injected
        if "{{" not in html:
            logger.warning("No template variables detected in extracted HTML")
