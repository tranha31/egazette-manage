# syntax=docker/dockerfile:1
# Frontend Egazette: build React (Vite) rồi phục vụ bằng nginx, đồng thời chuyển tiếp /api sang backend (cùng một địa chỉ,
# nên đăng nhập Basic và tải PDF hoạt động như khi chạy một cổng).

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Mặc định gọi /api cùng origin. Chỉ đặt khi API nằm ở địa chỉ khác (khi đó backend phải đặt CORS_ORIGINS).
ARG VITE_API_URL=
ENV VITE_API_URL=${VITE_API_URL}
RUN npm test && npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
