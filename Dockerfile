# Based on: https://github.com/astral-sh/uv-docker-example/blob/main/standalone.Dockerfile

## Builder image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Omit development dependencies
ENV UV_NO_DEV=1

# Configure the Python directory so it is consistent
ENV UV_PYTHON_INSTALL_DIR=/python

# Only use the managed Python version
ENV UV_PYTHON_PREFERENCE=only-managed
RUN uv python install 3.12

WORKDIR /scraper
# Copy instead of mount to allow rootless run, e.g. with podman
COPY pyproject.toml uv.lock /scraper/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
COPY . /scraper
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

#######################################################################################
## Final PaZuFa Scraper Image
FROM debian:trixie-slim@sha256:b6e2a152f22a40ff69d92cb397223c906017e1391a73c952b588e51af8883bf8

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    tesseract-ocr \
    tesseract-ocr-deu \
 && rm -rf /var/lib/apt/lists/*

# Setup a non-root user
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# Copy the Python version
COPY --from=builder /python /python

# Copy the application from the builder
COPY --from=builder --chown=nonroot:nonroot /scraper /scraper

# Place executables in the environment at the front of the path
ENV PATH="/scraper/.venv/bin:$PATH"

# Use the non-root user to run our application
USER nonroot

WORKDIR /scraper
ENTRYPOINT ["scrapy"]
