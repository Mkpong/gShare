# GShare per-node metrics agent.
FROM golang:1.27 AS builder
ARG TARGETOS
ARG TARGETARCH

WORKDIR /workspace
COPY go.mod go.mod
COPY go.sum go.sum
RUN go mod download

COPY cmd/ cmd/
COPY internal/ internal/

RUN CGO_ENABLED=0 GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH} \
	go build -a -o agent cmd/main.go

# Distroless nonroot: the agent only reads /sys/fs/cgroup, which is world-readable.
FROM gcr.io/distroless/static:nonroot
WORKDIR /
COPY --from=builder /workspace/agent .
USER 65532:65532

ENTRYPOINT ["/agent"]
