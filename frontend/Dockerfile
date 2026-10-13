FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Optional JSON array of ICE servers (e.g. to add TURN); empty = Google STUN
ARG VITE_ICE_SERVERS=""
ENV VITE_ICE_SERVERS=$VITE_ICE_SERVERS
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
