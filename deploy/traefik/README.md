# Bewaarhet Traefik

Minimal Docker-based Traefik reverse proxy for the production VPS.

It creates the `traefik_webgateway` Docker network expected by
`docker-compose.production.yml`, listens on ports 80 and 443, redirects HTTP to
HTTPS, and stores Let's Encrypt certificates in the `traefik_letsencrypt`
Docker volume.

Start on the VPS from the repository root:

```sh
docker compose -f deploy/traefik/docker-compose.yml up -d
docker compose -f docker-compose.production.yml up -d bewaarhet_site
docker compose --profile worker -f docker-compose.production.yml up -d bewaarhet_activation
```

The mail worker is not part of the Traefik compose file and is not restarted by
starting Traefik.
