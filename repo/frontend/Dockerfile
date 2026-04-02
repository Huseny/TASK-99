FROM node:20-alpine AS build

WORKDIR /web

COPY package.json /web/package.json
COPY tsconfig.json /web/tsconfig.json
COPY tsconfig.app.json /web/tsconfig.app.json
COPY tsconfig.node.json /web/tsconfig.node.json
COPY vite.config.ts /web/vite.config.ts
COPY index.html /web/index.html
COPY src /web/src

RUN npm install
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html

EXPOSE 80
