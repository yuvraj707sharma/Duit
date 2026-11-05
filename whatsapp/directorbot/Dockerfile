FROM node:20-alpine

WORKDIR /app

# Install system dependencies for native builds if needed
RUN apk add --no-cache python3 make g++ git

COPY package*.json ./
RUN npm install --production

COPY . .

RUN mkdir -p storage/auth_director storage/auth_bot storage/briefings

ENV PORT=5122
EXPOSE 5122

CMD ["node", "server.js"]
