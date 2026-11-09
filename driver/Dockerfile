# Static build served by nginx; /api is proxied to the api service. UNTESTED (decision 0020).
FROM node:20-alpine AS build
# Build context is the repository root, because the design tokens live in design/ (decision 0025).
WORKDIR /src/driver
COPY driver/package.json driver/package-lock.json ./
RUN npm ci
COPY design /src/design
COPY driver/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY driver/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/driver/dist /usr/share/nginx/html
