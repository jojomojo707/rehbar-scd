# rahbar-ui: the given chat page, served by non-root nginx on 8080.
# Build context: ui/   ->   docker build -t rahbar-ui:dev ui
FROM nginxinc/nginx-unprivileged:1.27.5-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html

# The base image already runs as nginx (uid 101); stated explicitly (section 4.7).
USER 101

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
