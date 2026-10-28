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

### RAG / document release (0004)

- Back up the current database before upgrading. The DB image now uses `pgvector/pgvector:pg17` (same PostgreSQL major version 17); keep the existing `postgres_data` volume. Do not change major versions in place.
- Configure `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_VERSION`, and `EMBEDDING_DIMENSIONS` together. The default is the multilingual `text-embedding-3-small` with 1536 dimensions. Missing/failed credentials leave documents in an explicit failed state; ordinary chat remains available. Custom OpenAI-compatible embedding endpoints must accept the `dimensions` parameter.
- Run `docker compose up -d --build`. The API runs Alembic before serving; `document-worker` starts only when the API is healthy. One API process and one document worker are intentional for this small deployment. The worker runs OCR locally with Japanese, simplified Chinese and English language packs; no external OCR service is used.
- `uploads_data` is a private volume shared by the API and worker only. Never mount it in the web container or expose it as an Nginx alias. Keep `UPLOAD_DIR=/app/uploads` with the supplied Compose file.
- The worker claims durable pending rows with `FOR UPDATE SKIP LOCKED`. Jobs interrupted for over 11 minutes become failed and can be retried. Parse subprocesses have CPU, address-space, file-size and wall-time limits; total indexing time is capped at 10 minutes. Very large/complex files can fail explicitly even within the upload-byte quota.
- The default upload limits are configurable in the env examples. Keep both Nginx `client_max_body_size` settings above `DOCUMENT_MAX_BYTES * DOCUMENT_BATCH_LIMIT` plus multipart overhead. Downloads require the same authenticated session as chat. API responses and downloads use `private, no-store`.
- Existing model profiles with old short defaults are migrated to an **8192-token per-model service budget**. This is a cost policy, not a claim about provider capacity. Set `max_output_tokens` (provider maximum), `default_output_tokens` (service budget) and `config_json.context_window_tokens` per profile to match the configured provider model. Generation reserves input/context space, and optionally applies `config_json.max_generation_cost_usd` using profile pricing. `MAX_OUTPUT_TOKENS` is an optional global cost cap; remove an old `MAX_OUTPUT_TOKENS=512` or `1024` deployment override to enable long answers. No shortness instruction remains in the default system prompt.
- `config_json.supports_vision` enables selected image inputs. The known Gemini 3.1 Flash-Lite profile is enabled by migration; other/overridden model IDs need an operator capability check before enabling it. Non-Vision models use OCR only and show a limitation notice. Visual requests accept up to five selected images; images are re-encoded and resized before provider transmission.
- Embedding model/version/dimension changes are never mixed in one search. Old documents report `requires_reindex`; use **Reprocess** to rebuild them. Exact vector search over the selected user's documents is intentional at the initial 50-file quota; no approximate index/reranker is required for this version.
- Every visible source is persisted from an actual selected retrieval result or actual supplied Vision image. A source panel lists candidate evidence, not a guarantee of model factual correctness. The prompt distinguishes document facts, inferences and general knowledge; no-match queries use a deterministic evidence-insufficient response. Provider truthfulness and prompt-injection resistance still need quality monitoring with real models.
- Usage rows retain token/cost accounting for successful and partial responses. If a cancelled/failed provider omits final usage, text tokens are estimated locally; image/reasoning billing can differ. Embedding usage and estimated cost are stored separately in `document_usage`; local OCR has no external API charge.

### Consistent backups and deletion

`backup.sh` briefly pauses API/web/worker writes, then saves `database.sql.gz`, `uploads.tar.gz`, and `SHA256SUMS` in one timestamped directory. A failed dump or archive does not publish a completed backup. `restore.sh /absolute/backup-directory` validates that set and restores both database and uploads; services stay stopped if restore fails. Legacy SQL-only backups do not contain attachments.

The shipped retention default is 7 days. Change retention and the user-facing privacy text together. Deleting a document removes the private original, chunks/vectors, and historical source relationships from the live service. Existing chat answer text is retained as conversation history; deleting a conversation also removes all its documents. Offline backup copies remain until retention expiry. Restoring an older snapshot can restore previously deleted content: before reopening the service, reapply deletions made after that snapshot using your operational deletion record. Restrict backup access and encrypt backups at the host/storage layer.
