#!/bin/sh
# HEADLESS=false (mặc định): Chromium chạy có giao diện trên màn hình ảo Xvfb, vì reCAPTCHA hay chặn trình duyệt headless.
# HEADLESS=true: không cần màn hình ảo.
set -e
case "$(printf '%s' "${HEADLESS:-false}" | tr 'A-Z' 'a-z')" in
  1|true|yes|on) ;;
  *)
    rm -f /tmp/.X99-lock                      # khoá cũ còn sót khi container khởi động lại
    Xvfb :99 -screen 0 1366x900x24 -nolisten tcp >/dev/null 2>&1 &
    export DISPLAY=:99
    ;;
esac
exec "$@"
