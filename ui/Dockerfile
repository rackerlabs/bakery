# Bakery UI Docker Image
#
# This Dockerfile builds the container image for the Bakery operator UI, which is
# deployed via the Helm chart. The image is published to GitHub Container Registry.
#
# Build: docker build -t ghcr.io/rackerlabs/bakery-ui:VERSION -f ui/Dockerfile .
# Push:  docker push ghcr.io/rackerlabs/bakery-ui:VERSION

FROM node:20-alpine AS build

WORKDIR /app/ui

COPY ui/package.json ui/package-lock.json ./
RUN npm ci

COPY ui/index.html ui/tsconfig.json ui/vite.config.ts ./
COPY ui/src ./src
RUN npm run build

FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production \
    NPM_CONFIG_UPDATE_NOTIFIER=false

RUN npm install --global serve@14.2.4

COPY --from=build /app/ui/dist /app

EXPOSE 8080

USER node

CMD ["serve", "-s", "/app", "-l", "8080"]
