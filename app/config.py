from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://sars_logbook:devpassword@localhost:55432/sars_logbook"
    app_secret_key: str = "dev-secret-not-for-production"
    public_base_url: str = "http://localhost:8090"
    google_maps_api_key: str = ""
    tax_year_start_month: int = 3
    tax_year_start_day: int = 1


settings = Settings()
