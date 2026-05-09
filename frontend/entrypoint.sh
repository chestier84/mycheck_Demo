#!/bin/bash
# Reemplazar variables de entorno en nginx.conf
envsubst < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Iniciar nginx
nginx -g 'daemon off;'
