# MinIO đã ngừng phát hành image / binary chính thức (Docker Hub, quay.io, dl.min.io đều báo lỗi), nên build thẳng từ
# mã nguồn của MinIO ở một tag cố định (https://github.com/minio/minio, giấy phép AGPL-3.0, dự án đã archived).
# Đổi phiên bản: docker compose build --build-arg MINIO_VERSION=<tag> minio
ARG GO_VERSION=1.25

FROM golang:${GO_VERSION}-alpine AS build
ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z
RUN apk add --no-cache git
RUN git clone --depth 1 --branch ${MINIO_VERSION} https://github.com/minio/minio.git /src
WORKDIR /src
# giống `make build` của MinIO: nhúng thông tin phiên bản vào binary
RUN CGO_ENABLED=0 go build -trimpath -ldflags "$(go run buildscripts/gen-ldflags.go) -s -w" -o /out/minio .

FROM alpine:3.21
RUN apk add --no-cache ca-certificates tzdata \
 && adduser -D -u 10001 minio \
 && mkdir /data && chown minio /data
COPY --from=build /out/minio /usr/bin/minio
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh
USER minio
VOLUME /data
EXPOSE 9000 9001
ENTRYPOINT ["/entrypoint.sh"]
CMD ["server", "/data", "--console-address", ":9001"]
