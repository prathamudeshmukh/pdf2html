from ..markdown_generator import MarkdownGenerator
from ..config import Settings


class MarkdownGeneratorFactory:
    @staticmethod
    def build(settings: Settings) -> MarkdownGenerator:
        return MarkdownGenerator(
            api_key=settings.openai_api_key,
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
        )
