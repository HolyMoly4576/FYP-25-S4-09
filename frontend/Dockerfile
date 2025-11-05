# Multi-stage: build then serve static
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json /app/
RUN npm ci || npm install
COPY . /app
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# Multi-stage: build then serve static
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json /app/
RUN npm ci || npm install
COPY . /app
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]


