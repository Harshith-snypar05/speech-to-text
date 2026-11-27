# Build context must be the repo root (STT/), not this directory -- this image needs both
# relays_phase7c/ and the vendored whisper.cpp/ source tree as siblings, matching the layout
# parakeet_relay.py expects at runtime (WHISPER_CPP = ROOT / "whisper.cpp").
#   docker build -f relays_phase7c/Dockerfile -t scriptliv-relay .
#
# The ~669MB Parakeet model is NOT baked into this image (see parakeet_relay.py's MODEL path) --
# mount it at /srv/whisper.cpp/models/ at runtime (see deploy/docker-compose.yml). CPU-only build
# by default; add -DGGML_CUDA=ON (needs the CUDA Toolkit in the build stage) once a GPU host is chosen.

FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends cmake make g++ git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY whisper.cpp ./whisper.cpp
WORKDIR /src/whisper.cpp
RUN cmake -B build-shared -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
        -DWHISPER_BUILD_EXAMPLES=OFF -DWHISPER_BUILD_TESTS=OFF \
    && cmake --build build-shared --target parakeet -j "$(nproc)"

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# The shared libs carry a build-time RPATH pointing at /src/..., which does not exist in this stage, so
# libparakeet.so cannot find libggml.so.0 on its own. Point the loader at where they were copied.
ENV LD_LIBRARY_PATH=/srv/whisper.cpp/build-shared/bin
# Listen on all interfaces inside the container (the app default is loopback-only, unreachable from the ALB).
ENV RELAY_HOST=0.0.0.0
# libgomp1: OpenMP runtime ggml's CPU backend links against.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY relays_phase7c/requirements.txt ./relays_phase7c/requirements.txt
RUN grep -vE '^(pytest|pytest-asyncio)' relays_phase7c/requirements.txt > /tmp/runtime.txt \
    && pip install --no-cache-dir -r /tmp/runtime.txt
COPY relays_phase7c ./relays_phase7c
COPY --from=build /src/whisper.cpp/build-shared/bin ./whisper.cpp/build-shared/bin
# models/ is where the mounted model volume lands (see docker-compose.yml) -- create it so the
# mount point exists with the right ownership before dropping root.
RUN mkdir -p ./whisper.cpp/models && useradd --system --uid 10002 relay && chown -R relay ./whisper.cpp/models
USER relay
WORKDIR /srv/relays_phase7c
EXPOSE 8772
CMD ["python", "parakeet_relay.py"]
