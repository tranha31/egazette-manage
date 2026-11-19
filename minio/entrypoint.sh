#!/bin/sh
# Không bao giờ chạy với key mặc định (minioadmin / minioadmin): bắt buộc phải đặt key riêng.
set -eu
if [ -z "${MINIO_ROOT_USER:-}" ] || [ -z "${MINIO_ROOT_PASSWORD:-}" ]; then
  echo "Thiếu MINIO_ROOT_USER / MINIO_ROOT_PASSWORD. Đặt MINIO_ACCESS_KEY và MINIO_SECRET_KEY trong file .env cạnh docker-compose.yml." >&2
  exit 1
fi
if [ "${MINIO_ROOT_USER}" = "minioadmin" ] || [ "${MINIO_ROOT_PASSWORD}" = "minioadmin" ]; then
  echo "Từ chối chạy với key mặc định 'minioadmin'. Hãy đặt key riêng." >&2
  exit 1
fi
exec /usr/bin/minio "$@"
