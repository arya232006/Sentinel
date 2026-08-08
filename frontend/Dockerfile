# Console: Next.js, served by its own Node process behind the reverse proxy.
#
# Not a static export. Both run views are dynamic routes (app/runs/[runId]/),
# and run ids only exist at runtime, so there is no set of paths to pre-render
# and `output: "export"` would fail the build.
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle by `next build`. They
# are build inputs, not runtime configuration: pointing the console at a
# different backend, or rotating the token, requires rebuilding this image.
# Setting them in the container's environment at `docker run` time does nothing.
ARG NEXT_PUBLIC_SENTINEL_API
ARG NEXT_PUBLIC_SENTINEL_TOKEN
ENV NEXT_PUBLIC_SENTINEL_API=$NEXT_PUBLIC_SENTINEL_API \
    NEXT_PUBLIC_SENTINEL_TOKEN=$NEXT_PUBLIC_SENTINEL_TOKEN

# Opts this build into `output: "standalone"`; see next.config.ts for why it is
# opt-in rather than always-on. The COPY of .next/standalone below is what
# needs it, so the flag belongs here and nowhere else.
ENV NEXT_OUTPUT_STANDALONE=1

RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The standalone bundle omits static assets and public/ by design; both have to
# be copied alongside it or every stylesheet and font 404s.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
