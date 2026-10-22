FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./
# node:20-alpine ships npm 10.8.2, which cannot `npm ci` a lockfile authored by npm 11.6.2:
# it re-resolves the optional platform bindings under @rolldown/binding-wasm32-wasi
# (@emnapi/core, @emnapi/runtime) to a newer version than the lock pins and EUSAGE-aborts.
# Pin npm to the version that generated package-lock.json so the clean install is identical
# on developer machines and in this image. Bump the pin together with a lockfile regeneration.
RUN npm install -g npm@11.6.2
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
