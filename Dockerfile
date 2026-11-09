# Stejný obraz pro vývoj i Railway. Verze zafixované (ověřeno 4. 11. 2026).
FROM python:3.15.2-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-deps -r requirements.txt

# Vyhledávací model (krok 2B) se stáhne jen při sestavení, mimo /app
# (ve vývoji je /app připojená složka). Za běhu nic nestahuje.
COPY scripts/stahni_model.py /tmp/stahni_model.py
# Čitelný i pro uživatele aplikace (safetensors ukládá jen pro vlastníka).
RUN python /tmp/stahni_model.py /opt/model && rm /tmp/stahni_model.py \
    && chmod -R a+rX /opt/model
ENV CESTA_MODELU=/opt/model \
    HF_HUB_OFFLINE=1

COPY . .
# Aplikace neběží pod rootem.
RUN useradd --uid 1000 --create-home aplikace && chmod +x scripts/*.sh
USER aplikace

EXPOSE 8000
# Migrace a pak server. Railway dosadí PORT.
CMD ["scripts/start.sh"]
