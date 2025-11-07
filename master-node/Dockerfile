FROM node:18-alpine

WORKDIR /app
COPY package.json ./
RUN apk add --no-cache python3 make gcc g++
RUN npm install
COPY . .
RUN mkdir -p /storage
EXPOSE 3000
CMD ["node", "server.js"]
