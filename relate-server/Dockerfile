# Pin the official release binary (there is no published server image).
# The binary links against glibc 2.39, which ships in Ubuntu 24.04
# (Debian bookworm's 2.36 is too old). Tested on linux/arm64.
FROM ubuntu:24.04 AS fetch
ARG RELATE_VERSION=1.0.1
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /dl
# Download the release asset for this architecture and verify its checksum.
RUN set -eux; \
    base="https://github.com/relatedb/relate/releases/download/v${RELATE_VERSION}"; \
    asset="relate-linux-${TARGETARCH}"; \
    curl -fsSL -o "$asset" "$base/$asset"; \
    curl -fsSL -o SHA256SUMS "$base/SHA256SUMS"; \
    grep " $asset\$" SHA256SUMS | sha256sum -c -; \
    install -m 0755 "$asset" /relate

FROM ubuntu:24.04
COPY --from=fetch /relate /usr/local/bin/relate
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV RELATE_AUTH=relate:hackathon \
    STORE_PATH=/data/graph
EXPOSE 7687 7474 7475
ENTRYPOINT ["/entrypoint.sh"]
