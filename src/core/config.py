from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow extra fields for testing
    )

    # API Configuration
    app_name: str = "Document Intelligence API"
    app_version: str = "0.1.0"
    app_env: str = Field(default="development", env="APP_ENV")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # OpenAI Configuration
    openai_api_key: str = Field(default="test-key", env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-3.5-turbo", env="OPENAI_MODEL")
    embedding_model: str = Field(
        default="text-embedding-ada-002", env="EMBEDDING_MODEL"
    )

    # Anthropic Configuration (optional)
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # ChromaDB Configuration
    chroma_host: str = Field(default="localhost", env="CHROMA_HOST")
    chroma_port: int = Field(default=8001, env="CHROMA_PORT")
    chroma_collection_name: str = Field(
        default="documents", env="CHROMA_COLLECTION_NAME"
    )

    # Document Processing Configuration
    max_upload_size: int = Field(default=10485760, env="MAX_UPLOAD_SIZE")  # 10MB
    chunk_size: int = Field(default=1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, env="CHUNK_OVERLAP")

    # Search Configuration
    search_top_k: int = Field(default=5, env="SEARCH_TOP_K")
    similarity_threshold: float = Field(default=0.7, env="SIMILARITY_THRESHOLD")

    # Paths
    data_dir: str = Field(default="./data", env="DATA_DIR")
    log_dir: str = Field(default="./logs", env="LOG_DIR")

    def __init__(self, **values):
        super().__init__(**values)
        # Create directories if they don't exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

    @property
    def chroma_url(self) -> str:
        """Get ChromaDB URL"""
        return f"http://{self.chroma_host}:{self.chroma_port}"

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.app_env.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.app_env.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Create a global settings instance
settings = get_settings()
