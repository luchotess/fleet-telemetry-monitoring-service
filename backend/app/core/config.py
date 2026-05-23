import os


class Settings:
    @property
    def database_url(self) -> str:
        return os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://fleet:fleet@localhost:5432/fleet",
        )

    @property
    def jwt_secret(self) -> str:
        return os.getenv("JWT_SECRET", "development-only-secret")

    @property
    def jwt_algorithm(self) -> str:
        return os.getenv("JWT_ALGORITHM", "HS256")

    @property
    def cors_origins(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "*")
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = Settings()
