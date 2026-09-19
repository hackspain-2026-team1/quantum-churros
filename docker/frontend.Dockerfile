FROM oven/bun:1.4.2-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# Rumbo (interfaz/): aplicación estática servida por el mismo servidor bajo /rumbo/.
# Lee el bundle de /data/v1/ y sus datos derivados de /data/rumbo/, ambos montados en el servidor.
FROM oven/bun:1.4.2-alpine AS rumbo
WORKDIR /app
COPY interfaz/package.json interfaz/bun.lock ./
RUN bun install --frozen-lockfile
COPY interfaz/ ./
RUN bun run check && bun run build:despliegue

FROM oven/bun:1.4.2-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/build ./build
COPY --from=rumbo /app/dist ./build/client/rumbo
COPY --from=build /app/package.json ./package.json
USER bun
EXPOSE 3000
CMD ["bun", "build/index.js"]
