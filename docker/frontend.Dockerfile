FROM oven/bun:1.4.2-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run check && bun run build:despliegue

FROM alpine:3.22 AS runtime
WORKDIR /app
RUN apk add --no-cache busybox-extras && addgroup -g 10001 rumbo && adduser -D -u 10001 -G rumbo rumbo
COPY --from=build --chown=rumbo:rumbo /app/dist ./dist
RUN mkdir -p ./dist/data/v1 ./dist/data/rumbo && chown -R rumbo:rumbo ./dist
USER rumbo
EXPOSE 3000
CMD ["httpd", "-f", "-p", "3000", "-h", "/app/dist"]
