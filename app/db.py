"""Připojení k databázi. Každý požadavek dostane vlastní sezení (transakci)."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.nastaveni import nastaveni


@lru_cache
def engine() -> Engine:
    return create_engine(nastaveni().database_url, pool_pre_ping=True, pool_size=5)


@lru_cache
def _tovarna() -> sessionmaker[Session]:
    return sessionmaker(engine(), expire_on_commit=False)


def nove_sezeni() -> Session:
    return _tovarna()()


def db() -> Iterator[Session]:
    """Závislost FastAPI: sezení databáze na jeden požadavek."""
    with nove_sezeni() as sezeni:
        yield sezeni
