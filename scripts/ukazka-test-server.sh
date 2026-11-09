#!/bin/sh
# Server živé ukázky pro testy (krok 6A): UKAZKA=1 nad vlastní čistou
# databází. Obnova připraví ukázkové účty se známým heslem a poprvé nahraje
# a přečte ukázkové dokumenty (skeny čte napodobenina), pak server na 8300.
set -e
case "$DATABASE_URL" in
  *_test*) ;;
  *) echo "Testovací server ukázky smí běžet jen nad databází s _test v názvu." >&2; exit 1 ;;
esac
python - <<'PY'
from sqlalchemy import text
from app.db import engine
with engine().begin() as s:
    s.execute(text("DROP SCHEMA public CASCADE"))
    s.execute(text("CREATE SCHEMA public"))
PY
alembic upgrade head
python -m app.prikazy obnov-ukazku
exec uvicorn app.main:app --host 0.0.0.0 --port 8300 \
  --proxy-headers --forwarded-allow-ips '*' --no-server-header
