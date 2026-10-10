FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/requirements.txt /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /app/media /app/staticfiles /app/.private/documents /app/.private/announcements /home/app/.cache \
    && chown -R app:app /app /home/app/.cache

COPY --chown=app:app backend/ /app/backend/
COPY --chmod=755 docker/backend/entrypoint.sh /usr/local/bin/smartlms-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/smartlms-entrypoint

USER app
EXPOSE 8000

ENTRYPOINT ["smartlms-entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
