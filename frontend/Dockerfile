FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
# Optimize npm for VPS/Droplets: use npm ci (uses package-lock.json directly) with socket caps
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set maxsockets 5 \
    && npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]