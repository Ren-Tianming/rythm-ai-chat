# t4g.small production deployment

Target topology:

```text
Internet
  -> shared host Nginx :80/:443
  -> Host chat.rhythmusic.site
  -> 127.0.0.1:8081
  -> Chatbot web container :80
  -> backend + PostgreSQL on a private Docker network
```

The Compose stack never binds a public interface. The Session and CSRF cookies
are named `rythm_session` and `rythm_csrf`, have no `Domain` attribute, and are
therefore Host-only for `chat.rhythmusic.site`.

## Host baseline

- Ubuntu 24.04 ARM64 or Amazon Linux 2023 ARM64.
- Encrypted gp3 EBS volume with at least 20 GiB.
- Security group inbound: 22 only from an administrator IP, plus 80 and 443.
- Docker Engine with Compose v2, host Nginx, Certbot, and a 2 GiB swap file.
- DNS A/AAAA records for `chat.rhythmusic.site` pointing to the host.

Keep at least 600 MiB of memory available for the kernel, Nginx, Docker, SSH,
and monitoring. The Compose limits are deliberately conservative for a 2 GiB
host and the API runs one worker.

## Install

```bash
sudo install -d -o "$USER" -g "$USER" /opt/rythm-chatbot
git clone <repository-url> /opt/rythm-chatbot
cd /opt/rythm-chatbot
cp deploy/.env.production.example .env
chmod 600 .env
```

Generate independent database and application secrets, then fill every
placeholder in `.env`:

```bash
openssl rand -base64 48
openssl rand -base64 36
```

At least one Provider must have both an API key and an explicit model ID.
Turnstile must allow `chat.rhythmusic.site`. SMTP credentials and the sender
domain must be production-ready.

Start the private stack:

```bash
docker compose config -q
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8081/api/v1/health/ready
```

## Shared Nginx and TLS

Install `deploy/nginx/chat.rhythmusic.site.conf` in the host Nginx configuration.
Obtain the first certificate before enabling the final 443 block, then test and
reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Only the shared host Nginx listens on ports 80 and 443. Do not expose port 8081
in the security group.

## Backups

Install the service and timer:

```bash
sudo install -m 0755 deploy/backup.sh /opt/rythm-chatbot/deploy/backup.sh
sudo install -m 0755 deploy/restore.sh /opt/rythm-chatbot/deploy/restore.sh
sudo install -m 0644 deploy/rythm-chatbot-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/rythm-chatbot-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rythm-chatbot-backup.timer
sudo systemctl start rythm-chatbot-backup.service
```

Copy backups to encrypted off-host storage after creation. Test
`deploy/restore.sh` monthly on an isolated host. A local backup on the same EBS
volume does not protect against volume loss.

## Release

Before each release:

```bash
docker compose exec -T db pg_isready
sudo systemctl start rythm-chatbot-backup.service
git pull --ff-only
docker compose build
docker compose up -d
curl --fail https://chat.rhythmusic.site/api/v1/health/ready
```

Retain the previous Git commit and image until smoke testing passes. Review
container memory, disk, restart count, 5xx rate, Provider failures, email
delivery, Turnstile failures, daily Token use, and TLS expiry.
