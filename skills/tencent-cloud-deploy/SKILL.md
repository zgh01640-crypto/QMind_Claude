---
name: tencent-cloud-deploy
description: Deploy and operate this QMind Docker Compose application on a Tencent Cloud Linux CVM, including first deployment, database/file migration, CI release, health checks, backups, and rollback.
metadata:
  short-description: One-click Tencent Cloud deployment for QMind
---

# Tencent Cloud deployment

Use this skill when the user asks to deploy, update, migrate, back up, roll back, or set up continuous deployment for this QMind repository on a Tencent Cloud CVM.

## Operating rules

- Treat `/opt/qmind/shared/.env.production` as server-only secret material. Never commit or package it.
- Keep PostgreSQL and API private to the Compose network. Only Nginx should be exposed on TCP 80/443.
- Never run `docker compose down -v`, remove the PostgreSQL data directory, or overwrite a backup without explicit authorization.
- Before a data migration, create a PostgreSQL custom-format dump and archive `data/api/pricing-kb-uploads` separately.
- For OpenCloudOS/SELinux, preserve the `:Z` bind-mount labels in `docker-compose.prod.yml`.
- Use `deploy/tencent-cloud/deploy.sh` for idempotent deployment and health validation. Use `backup.sh` before migrations or risky releases and `rollback.sh` only after a failed release or explicit rollback request.

## Modes

1. **First deployment**: create `/opt/qmind/shared/.env.production`, install the Nginx config from `deploy/nginx/qmind.conf`, then run the deployment script against the checked-out release.
2. **Data migration**: stop API/Web writes, run `pg_dump -Fc` locally, transfer the dump and knowledge-base archive, restore with `pg_restore`, extract uploads into `/opt/qmind/data/api`, and redeploy. Verify record counts and `/api/periods` before reopening traffic.
3. **Continuous deployment**: use `.github/workflows/deploy.yml`. Configure `TENCENT_HOST`, `TENCENT_USER`, `TENCENT_SSH_KEY`, and optionally `TENCENT_PORT`/`TENCENT_APP_DIR` as GitHub secrets or variables. Keep `.env.production` on the server.
4. **Operations**: run `backup.sh` for a timestamped dump and checksum; inspect Compose logs and the health endpoint after every release; use `rollback.sh` to switch to the previous release.

## Repository resources

- Production services and persistence: `docker-compose.prod.yml`
- Secret template: `.env.production.example`
- Server scripts: `deploy/tencent-cloud/*.sh`
- Nginx entrypoint: `deploy/nginx/qmind.conf`
- CI workflow and required secrets: `.github/workflows/deploy.yml` and [references/github-actions.md](references/github-actions.md)
