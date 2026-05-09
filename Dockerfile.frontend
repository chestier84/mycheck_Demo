FROM nginx:alpine

COPY datafix_oracle.html /usr/share/nginx/html/index.html
COPY backend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
