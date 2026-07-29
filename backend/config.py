from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Rutas del sistema
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    
    # Taxonomía
    TAXONOMY_PATH: Path = BASE_DIR / "backend" / "infrastructure" / "knowledge" / "taxonomy.yaml"
    
    # IA (la pondremos aquí para futuro)
    OPENAI_API_KEY: str = ""
    AI_PROVIDER: str = "openai"  # 'openai', 'ollama', 'mock'
    
    # Umbrales de confianza
    CONFIDENCE_THRESHOLD: float = 0.7
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
