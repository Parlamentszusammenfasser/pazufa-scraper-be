# Dockerfile to run the scraper via podman on macOS
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:a2e8b64aed3382a20c03fc6f1e03fe95fb312425e071ad27d7936a0f02c3e497

WORKDIR /scraper

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install only production dependencies (no dev group)
RUN uv sync --no-dev --frozen

# Rebuild cryptography from source to compensate missing functionality in the vm virtual cpu
RUN apt-get update && apt-get install -y --no-install-recommends gcc libssl-dev libffi-dev curl \
     && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal \
     && . "$HOME/.cargo/env" \
     && RUSTFLAGS="-C target-cpu=cortex-a53" uv pip install --no-binary cryptography cryptography \
     && apt-get purge -y curl \
     && rm -rf /var/lib/apt/lists/* "$HOME/.cargo/registry" "$HOME/.rustup"
# cortex-a53 is a baseline ARMv8.0 core without optional crypto extensions (AES, SHA), so the resulting .so will run on any ARM64 CPU regardless of what features the Podman VM exposes.

# Install libmagic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    tesseract-ocr \
    tesseract-ocr-deu \
 && rm -rf /var/lib/apt/lists/*

# Copy the project source
COPY pazufa_scraper_be/ ./pazufa_scraper_be/
COPY scrapy.cfg ./

# disabling ARM hardware acceleration in OpenSSL, slightly slower but stable.
ENV OPENSSL_armcap=0

ENV WAHLPERIODE=19
ENV PAZUFA_API_BASE_URL=http://localhost:8080
ENV LOG_LEVEL=INFO
# PAZUFA_API_TOKEN / PAZUFA_LLM_TOKEN should be injected via `-e`

CMD uv run --no-dev --frozen scrapy runspider -s LOG_LEVEL=${LOG_LEVEL} -s WAHLPERIODE=${WAHLPERIODE} pazufa_scraper_be/spiders/gesetz_vorgang.py 2>&1
