from ..config import get_settings, Settings

class SettingsConfigurator:
    @staticmethod
    def configure(request) -> Settings:
        settings = get_settings()
        settings.model = request.model
        settings.dpi = request.dpi
        settings.max_tokens = request.max_tokens
        settings.temperature = request.temperature
        settings.max_parallel_workers = request.max_parallel_workers
        settings.css_mode = request.css_mode
        return settings
