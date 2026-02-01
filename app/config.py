from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


class Settings(BaseSettings):
    ENV: str = "development"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_ANON_KEY: str

    PUBLIC_API_URL: str = "http://127.0.0.1:8000"

    GROQ_API_KEY: str
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    MODEL_NAME: str

    CONSUMER_KEY: str
    CONSUMER_SECRET: str

    class Config:
        env_file = str(ENV_PATH)
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "forbid"


settings = Settings()