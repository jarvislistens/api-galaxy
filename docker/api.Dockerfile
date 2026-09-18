# The backend. Slim base plus the system libraries WeasyPrint and CairoSVG need for the
# PDF and PNG exports — without them those two formats correctly report themselves as
# unavailable, which works but is a worse experience than just installing them.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
      libffi8 shared-mime-info curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/api_galaxy apps/api/api_galaxy
COPY packages/report-runtime packages/report-runtime
COPY samples samples

RUN pip install --no-cache-dir -e "apps/api[pdf,png]"

ENV API_GALAXY_HOST=0.0.0.0 API_GALAXY_PORT=8099 API_GALAXY_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8099

CMD ["python", "-m", "uvicorn", "api_galaxy.app.main:app", \
     "--host", "0.0.0.0", "--port", "8099", "--app-dir", "apps/api"]
