# Testy v prohlížeči. Verze obrazu = verze playwright v testy/requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
WORKDIR /prace
COPY requirements.txt /tmp/requirements.txt
RUN pip install --break-system-packages --no-cache-dir -r /tmp/requirements.txt
