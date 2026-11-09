# Výroba vymyšlených PDF JK pojišťovny (krok 1C). Nástroj jen pro vývoj,
# do obrazu aplikace nepatří. Spuštění: docker compose --profile dokumenty run --rm dokumenty
FROM python:3.15.2-slim-trixie

# Písmo s českou diakritikou (DejaVu) a „ručně“ vyplněné údaje na skenech
# hlášení škody (Comic Neue — jediné písmo podobné rukopisu v Debianu, které
# umí ě, ř, ů; ověřeno 4. 11. 2026), verze z Debianu trixie.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core=2.37-8 fonts-comic-neue=2.51-4 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-deps -r /tmp/requirements.txt

WORKDIR /prace
