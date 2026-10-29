from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "openai/gpt-oss-120b"
    openai_base_url: str = "https://api.groq.com/openai/v1"
    database_url: str = "sqlite:///./dreamtalk.db"
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
