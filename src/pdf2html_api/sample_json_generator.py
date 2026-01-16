import json
import logging
from pathlib import Path
from openai import OpenAI

logger = logging.getLogger(__name__)


class SampleJSONGenerator:
    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        prompt_path = Path(__file__).resolve().parent / "prompts" / "html_to_sample_json.md"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def generate(self, html_with_variables: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": html_with_variables
                }
            ]
        )

        content = response.choices[0].message.content.strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON returned by LLM for sample JSON generation")
            raise ValueError("LLM returned invalid JSON for sample generation") from e

        if not isinstance(result, dict):
            raise ValueError("Sample JSON output must be a flat JSON object")

        return result
