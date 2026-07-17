FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
ARG VITE_TURNSTILE_SITE_KEY=""
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
