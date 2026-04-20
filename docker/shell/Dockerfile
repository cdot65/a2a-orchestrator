FROM alpine:3.20

RUN apk add --no-cache \
    bash \
    coreutils \
    findutils \
    grep \
    sed \
    jq \
    ripgrep \
    busybox-extras

RUN adduser -D -u 10001 sandbox
USER sandbox
WORKDIR /work

SHELL ["/bin/sh", "-c"]
