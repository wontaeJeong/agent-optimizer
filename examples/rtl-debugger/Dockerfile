FROM node:22-bookworm-slim
ARG OPENCODE_VERSION
RUN test -n "$OPENCODE_VERSION" && npm install -g "opencode-ai@$OPENCODE_VERSION"
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /work
