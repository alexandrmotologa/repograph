FROM python:3.12-slim-bookworm

LABEL maintainer="Alexandru Motologa"
LABEL description="RepoGraph: Local-First Codebase Knowledge Graph & Blast-Radius Engine"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
RUN pip install --upgrade pip && \
    pip install .

COPY src/ /app/src/
RUN pip install -e .

RUN useradd -m -u 1000 repouser && \
    chown -R repouser:repouser /app

USER repouser

EXPOSE 8765

ENTRYPOINT ["repograph"]
CMD ["--help"]
