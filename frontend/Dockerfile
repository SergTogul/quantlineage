FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Local demo default: browser talks to host-published API. Shared Compose
# passes VITE_API_BASE_URL=same-origin so the SPA uses Caddy /api/*.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Unprivileged nginx: listen on 80 (Compose maps 127.0.0.1:5173:80). Docker's
# default CAP_NET_BIND_SERVICE lets the nginx user bind privileged ports.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html
USER nginx
