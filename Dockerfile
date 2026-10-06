# syntax=docker/dockerfile:1
# Game Pilot appliance (appliance image design, ruling 3): the dashboard supervises the pilot.
FROM rust:1-slim-bookworm AS rust
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN cargo build --release -p game-controller && strip target/release/game-controller

FROM python:3.13-slim-bookworm AS py
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY pyproject.toml constraints.txt /tmp/
# runtime dependencies only, from pyproject, at the versions the tests ran against (constraints.txt) (the package itself runs from /app/src)
RUN /opt/venv/bin/python - <<'PY'
import subprocess, tomllib
deps = tomllib.load(open("/tmp/pyproject.toml", "rb"))["project"]["dependencies"]
subprocess.check_call(["/opt/venv/bin/pip", "install", "-c", "/tmp/constraints.txt", *deps])
PY
# the runtime never installs anything: drop pip and its scripts
RUN /opt/venv/bin/pip uninstall -y pip >/dev/null 2>&1; rm -rf /opt/venv/lib/python3.13/site-packages/pip* /opt/venv/bin/pip* \
 && find /opt/venv -name __pycache__ -prune -exec rm -rf {} +

FROM python:3.13-slim-bookworm AS runtime
ARG LITESTREAM_VERSION=0.5.17
ARG LITESTREAM_SHA256=cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates curl \
 && curl -fsSL -o /tmp/ls.tar.gz "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.tar.gz" \
 && echo "${LITESTREAM_SHA256}  /tmp/ls.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/ls.tar.gz --no-same-owner -C /usr/local/bin litestream && rm /tmp/ls.tar.gz \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10010 pilot && useradd -u 10010 -g 10010 -M -d /data -s /usr/sbin/nologin pilot
COPY --from=py /opt/venv /opt/venv
COPY --from=rust /src/target/release/game-controller /app/bin/game-controller
COPY corpora /app/corpora
COPY src /app/src
COPY docker /app/docker
RUN printf '#!/bin/sh\nexec /opt/venv/bin/python -m pilot "$@"\n' > /usr/local/bin/pilot \
 && chmod 0755 /usr/local/bin/pilot /app/docker/entrypoint.sh \
 && install -d -o 10010 -g 10010 -m 0700 /data
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 PYDANTIC_AI_NO_BANNER=1 \
    PILOT_DATA_DIR=/data PILOT_CORPORA_DIR=/app/corpora PILOT_CONTROLLER_BIN=/app/bin/game-controller
USER 10010:10010
WORKDIR /app
EXPOSE 8780
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD /opt/venv/bin/python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8780/healthz', timeout=3).read() == b'ok' else 1)"
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]
