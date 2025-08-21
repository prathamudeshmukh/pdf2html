"""Configuration management for PDF2HTML API."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator, model_validator

# Load environment variables from .env file if it exists
load_dotenv()


class Settings(BaseModel):
    """Application settings with environment variable support."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(default="", description="OpenAI API key")
    model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    max_tokens: int = Field(default=4000, description="Maximum tokens for LLM response")
    temperature: float = Field(default=0.0, description="LLM temperature setting")
    
    # PDF Processing
    dpi: int = Field(default=200, description="Image resolution for PDF rendering")
    
    # Output Configuration
    css_mode: Literal["grid", "columns", "single"] = Field(default="grid", description="CSS layout mode")
    
    # Performance Configuration
    max_parallel_workers: int = Field(default=3, description="Maximum number of parallel workers for page processing")
    
    def __init__(self, **data):
        """Initialize settings with environment variable support."""
        # Check for API key in environment if not provided
        if 'openai_api_key' not in data or not data['openai_api_key'] or data['openai_api_key'] == "sk-your-api-key-here":
            env_key = os.getenv("OPENAI_API_KEY")
            if not env_key:
                raise ValueError(
                    "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                    "or provide it in .env file"
                )
            data['openai_api_key'] = env_key
        
        super().__init__(**data)
    
    @validator("model", pre=True)
    def validate_model(cls, v):
        """Validate and load model from environment if not provided."""
        if not v:
            return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return v
    
    @validator("dpi")
    def validate_dpi(cls, v):
        """Validate DPI is within reasonable bounds."""
        if v < 72 or v > 600:
            raise ValueError("DPI must be between 72 and 600")
        return v
    
    @validator("max_tokens")
    def validate_max_tokens(cls, v):
        """Validate max tokens is within reasonable bounds."""
        if v < 100 or v > 8000:
            raise ValueError("max_tokens must be between 100 and 8000")
        return v
    
    @validator("temperature")
    def validate_temperature(cls, v):
        """Validate temperature is within bounds."""
        if v < 0.0 or v > 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v
    
    @validator("max_parallel_workers")
    def validate_max_parallel_workers(cls, v):
        """Validate max parallel workers is within reasonable bounds."""
        if v < 1 or v > 10:
            raise ValueError("max_parallel_workers must be between 1 and 10")
        return v


def get_settings() -> Settings:
    """Get application settings."""
    return Settings() 