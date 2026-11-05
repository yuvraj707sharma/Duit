FROM node:20.18.0-alpine3.20

WORKDIR /app

# Install system dependencies for native builds if needed
RUN apk add --no-cache python3 make g++ git

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

RUN mkdir -p storage/auth_director storage/auth_bot storage/briefings

ENV PORT=5122
EXPOSE 5122

CMD ["node", "server.js"]

