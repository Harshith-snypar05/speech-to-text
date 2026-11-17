FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* values are baked into the browser bundle at build time
ARG NEXT_PUBLIC_WS_URL=
ARG NEXT_PUBLIC_SL_API_BASE=/sl
# next.config.ts rewrites /sl/* to this address; Next bakes rewrites in at build time
ARG SL_BACKEND_HTTP=http://api:8790
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL NEXT_PUBLIC_SL_API_BASE=$NEXT_PUBLIC_SL_API_BASE SL_BACKEND_HTTP=$SL_BACKEND_HTTP NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./
USER node
EXPOSE 3100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD wget -qO- http://127.0.0.1:3100/ >/dev/null || exit 1
CMD ["npx", "next", "start", "-p", "3100"]
