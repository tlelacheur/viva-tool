FROM node:22-alpine AS builder

# Restrict Node heap memory to 512MB and threadpool to 2 to prevent OOM / CPU lockup on low-RAM VPS
ENV NODE_OPTIONS="--max-old-space-size=512"
ENV UV_THREADPOOL_SIZE=2

WORKDIR /app
COPY package*.json ./

# Low-resource npm config for 1GB/2GB VPS droplets (maxsockets=2)
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set maxsockets 2 \
    && npm ci --no-audit --no-fund --prefer-offline

COPY . .
RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
       -keyout /etc/nginx/certs/key.pem \
       -out /etc/nginx/certs/cert.pem \
       -subj "/C=US/ST=State/L=City/O=VivaTool/CN=viva-tool.local"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]