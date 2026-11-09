"""Spouštění migrací. Adresa databáze jen z prostředí, nikdy z ini souboru."""

from logging.config import fileConfig

from alembic import context

from app.db import engine
from app.modely import Zaklad

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

with engine().connect() as spojeni:
    context.configure(connection=spojeni, target_metadata=Zaklad.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
