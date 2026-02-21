from ..llm import HTMLGenerator
from ..config import Settings

class HTMLGeneratorFactory:
    @staticmethod
    def build(settings: Settings) -> HTMLGenerator:
        return HTMLGenerator(
            api_key=settings.openai_api_key,
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
        )
