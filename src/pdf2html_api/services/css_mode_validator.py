_VALID_CSS_MODES = frozenset({"grid", "columns", "single"})

class CSSModeValidator:
    @staticmethod
    def validate(css_mode: str) -> None:
        if css_mode not in _VALID_CSS_MODES:
            raise ValueError(
                f"CSS mode must be one of {sorted(_VALID_CSS_MODES)}, "
                f"got '{css_mode}'"
            )
