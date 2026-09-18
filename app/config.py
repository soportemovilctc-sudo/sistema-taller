"""Configuración de la aplicación cargada desde variables de entorno (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "cambia-esta-clave-super-secreta-larga-y-unica"
    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./taller.db"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
