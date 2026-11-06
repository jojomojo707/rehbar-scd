# rahbar-ui: the given chat page, served by non-root nginx on 8080.
# Build context: ui/   ->   docker build -t rahbar-ui:dev ui
FROM nginxinc/nginx-unprivileged:1.30.6-alpine3.24

# Alpine security fixes newer than the base image (Trivy, section 6: brotli, curl, expat).
# apk needs root; the image switches back to the nginx user below.
USER root
RUN apk upgrade --no-cache

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html

# The base image already runs as nginx (uid 101); stated explicitly (section 4.7).
USER 101

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
