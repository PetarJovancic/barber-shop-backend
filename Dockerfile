FROM debian:bookworm-slim

LABEL maintainer=backend-services@g2m.com

RUN apt-get update && \
    apt-get install -y curl git build-essential python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

COPY . /src

ENV PATH="/root/.local/bin/:$PATH"
RUN uv sync --no-dev

CMD uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
