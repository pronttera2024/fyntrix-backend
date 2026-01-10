from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://fyntrix_auth:changeme@localhost:5432/fyntrix_auth"
    oidc_issuer: AnyHttpUrl
    oidc_audience: str
    oidc_jwks_url: AnyHttpUrl

    class Config:
        env_prefix = "FYNTRIX_AUTH_"
        env_file = ".env"


settings = Settings()
