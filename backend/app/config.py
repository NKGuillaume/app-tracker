from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/auth/callback"

    supabase_url: str
    supabase_service_role_key: str

    openai_api_key: str

    session_secret_key: str
    token_encryption_key: str

    frontend_origin: str = "http://localhost:5173"

    gmail_pubsub_topic: str | None = None
    google_cloud_project: str | None = None

    # "development" allows non-Secure session cookies for plain-http localhost;
    # set to "production" once deployed behind HTTPS.
    environment: str = "development"

    @property
    def cookies_secure(self) -> bool:
        return self.environment == "production"


settings = Settings()
