#!/bin/sh
# Server pro testy v prohlížeči: čistá testovací databáze, migrace,
# účty s náhodnými hesly pro tenhle běh, pak server na portu 8100.
set -e
case "$DATABASE_URL" in
  *_test*) ;;
  *) echo "Testovací server smí běžet jen nad databází s _test v názvu." >&2; exit 1 ;;
esac
python - <<'PY'
from sqlalchemy import text
from app.db import engine
with engine().begin() as s:
    s.execute(text("DROP SCHEMA public CASCADE"))
    s.execute(text("CREATE SCHEMA public"))
PY
alembic upgrade head
python -m app.prikazy testove-ucty --soubor /stav/ucty.json
# Deset PDF JK pojišťovny (krok 1C) pro testy vyhledávání; hesla jejich
# klientů se v testech nepoužívají.
python -m app.prikazy ukazkove-dokumenty
# Evaluace (krok 5A) nad čistými dokumenty, než je testy začnou měnit.
# Odpovědi jdou hromadnou dávkou do napodobeniny; výsledek čte
# testy/test_evaluace.py.
python -m app.prikazy evaluace --odpovedi --vystup /stav/evaluace.json > /dev/null
# Testy posílají náhodnou X-Forwarded-For, aby se omezení pokusů
# o přihlášení mezi testy nepletlo (před testovacím serverem není proxy).
exec uvicorn app.main:app --host 0.0.0.0 --port 8100 \
  --proxy-headers --forwarded-allow-ips '*' --no-server-header
