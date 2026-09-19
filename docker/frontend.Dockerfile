FROM oven/bun:1.4.2-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run check && bun run build:despliegue

FROM alpine:3.22 AS runtime
WORKDIR /app
RUN apk add --no-cache nginx libstdc++ libgcc && addgroup -g 10001 rumbo && adduser -D -u 10001 -G rumbo rumbo
COPY --from=build --chown=rumbo:rumbo /app/dist ./dist
# bun viaja también en la imagen de ejecución: el modo dev del compose lo
# necesita para correr `bun install && bun run dev` sobre ./frontend montado.
COPY --from=build /usr/local/bin/bun /usr/local/bin/bun
COPY docker/web.nginx.conf /etc/nginx/nginx.conf
RUN mkdir -p ./dist/data/v1 ./dist/data/rumbo /tmp/nginx && chown -R rumbo:rumbo ./dist /tmp/nginx
USER rumbo
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
