"""Nastavení aplikace z proměnných prostředí.

Tajemství (připojení k databázi) se nikdy nedosazuje náhradní hodnotou —
když chybí, aplikace nenaběhne.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Nastaveni(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # postgresql+psycopg://uzivatel:heslo@server:5432/databaze
    database_url: str = Field(min_length=10)

    @field_validator("database_url")
    @classmethod
    def _ovladac_psycopg(cls, adresa: str) -> str:
        """Adresa ze skriptu nova-databaze (postgresql://…) dostane ovladač
        psycopg, který je v obrazu — jinak by SQLAlchemy hledala psycopg2."""
        for zacatek in ("postgresql://", "postgres://"):
            if adresa.startswith(zacatek):
                return "postgresql+psycopg://" + adresa[len(zacatek):]
        return adresa

    # Cookie sezení jen přes HTTPS. Vypíná se jen ve vývoji a v testech.
    cookie_secure: bool = True
    # Největší nahrávaný soubor v MB.
    max_upload_mb: int = Field(default=10, ge=1, le=50)
    # Klíč k Anthropicu (Claude Haiku čte skeny). Tajemství — jen v prostředí.
    # Prázdný = OCR vypnuté, sken počká ve stavu „čeká na OCR“.
    anthropic_api_key: str = ""
    # Jen pro testy (napodobenina Anthropicu v Dockeru). Na Railway se nezadává.
    anthropic_base_url: str | None = None
    # Pojistka útraty: delší sken se Claudovi neposílá.
    ocr_max_stran: int = Field(default=20, ge=1, le=100)
    # Vyhledávací model (model2vec) v obrazu, stažený při sestavení (krok 2B).
    cesta_modelu: str = "/opt/model"
    # Denní limity asistenta (Jakub, 3. 11. 2026): na účet a celkem za den.
    ai_limit_ucet: int = Field(default=20, ge=1, le=1000)
    ai_limit_celkem: int = Field(default=100, ge=1, le=10000)
    # Živá ukázka (krok 6A): ukázkové účty se známým heslem, noční obnova,
    # nahrávání a mazání vypnuté. Zapíná Jakub na Railway (UKAZKA=1).
    ukazka: bool = False
    # V ukázce se limit počítá na návštěvníka (adresu), ne na sdílený účet
    # (Jakub, 8. 11. 2026).
    ai_limit_navstevnik: int = Field(default=10, ge=1, le=1000)
    # Jen pro testy: obnova ukázky na požádání hlavičkou X-Obnova-Ukazky.
    # Na Railway se nezadává.
    ukazka_test_obnova: bool = False


@lru_cache
def nastaveni() -> Nastaveni:
    return Nastaveni()  # type: ignore[call-arg]
