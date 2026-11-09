#!/bin/sh
# Produkční start: migrace databáze a server.
set -e
alembic upgrade head
# Živá ukázka (UKAZKA=1, krok 6A): ukázkové účty, poprvé dokumenty, obnova dne.
if [ "$UKAZKA" = "1" ] || [ "$UKAZKA" = "true" ]; then
  python -m app.prikazy obnov-ukazku
fi
# --proxy-headers: adresa klienta z X-Forwarded-For od proxy Railway
# (potřebuje ji omezení pokusů o přihlášení).
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips '*' --no-server-header
