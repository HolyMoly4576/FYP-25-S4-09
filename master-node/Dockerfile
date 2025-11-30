FROM node:18-alpine

WORKDIR /app
COPY package.json ./
RUN apk add --no-cache python3 make gcc g++ sqlite curl
RUN npm install
COPY . .
RUN mkdir -p /storage
RUN mkdir -p /data
EXPOSE 3000
CMD ["node", "server.js"]
