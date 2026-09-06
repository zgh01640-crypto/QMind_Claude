# GitHub Actions setup

The workflow packages the committed repository, uploads a release archive over SSH, extracts it under `/opt/qmind/releases/<commit>`, atomically switches `/opt/qmind/current`, and invokes `deploy/tencent-cloud/deploy.sh`.

Configure these repository secrets or variables:

- `TENCENT_HOST`: CVM public IP or DNS name.
- `TENCENT_USER`: deployment user, normally `ths`.
- `TENCENT_SSH_KEY`: private key whose public key is in the server user's `~/.ssh/authorized_keys`.
- `TENCENT_PORT`: optional, defaults to `22`.
- `TENCENT_APP_DIR`: optional, defaults to `/opt/qmind`.

Create `/opt/qmind/shared/.env.production` manually on the server before the first workflow run. The workflow deliberately does not transmit application secrets.

The no-source workflow is `.github/workflows/image-deploy.yml`; it triggers on `codex/kb-versioning` and supports `workflow_dispatch`. It builds and pushes `qmind-api` and `qmind-web` to TCR, transfers only the Compose file and deployment scripts, logs the server into TCR, then pulls the commit-SHA images. A failed health check fails the job; it does not delete data or automatically roll back. Review logs, then run `image-rollback.sh <commit-sha>` on the server when the previous release is known to be safe.
