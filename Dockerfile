FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY pyproject.toml README.md ./
COPY configs ./configs
COPY docs ./docs
COPY scripts ./scripts
COPY project_tools ./project_tools
COPY src ./src

ARG EXTRA=research
RUN if [ "$EXTRA" = "base" ] || [ -z "$EXTRA" ]; then \
        uv pip install --system -e .; \
    else \
        uv pip install --system -e ".[${EXTRA}]"; \
    fi

ENTRYPOINT ["moneytrees"]
CMD ["--help"]
