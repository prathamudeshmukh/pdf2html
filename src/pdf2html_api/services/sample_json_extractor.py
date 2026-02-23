import json
import logging
from pathlib import Path
from openai import OpenAI

logger = logging.getLogger(__name__)


class SampleJSONExtractor:
    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "html_to_sample_json.md"
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def extract(self, html: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"HTML:\n{html}"}
            ]
        )

        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if the LLM wraps the response in ```json ... ```
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]  # drop the opening ```json line
            content = content.rsplit("```", 1)[0].strip()  # drop the closing ```

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON returned by LLM: {content}")
            raise ValueError("LLM returned invalid JSON") from e

        if not isinstance(data, dict):
            raise ValueError("Sample JSON must be an object")

        return data