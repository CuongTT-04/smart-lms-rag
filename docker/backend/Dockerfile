FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app

COPY --chown=app:app backend/ /app/backend/
COPY --chmod=755 docker/backend/entrypoint.sh /usr/local/bin/smartlms-entrypoint

USER app
EXPOSE 8000

ENTRYPOINT ["smartlms-entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
