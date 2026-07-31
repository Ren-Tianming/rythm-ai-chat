# RyThM Chatbot / 天铭聊天机器人
<p align="center">
  <img src="frontend/public/rythm-logo.png" alt="RyThM Music logo" width="180">
</p>

RyThM Chatbot is a multilingual, multi-provider AI chat MVP built for low-cost deployment without giving up the engineering foundations needed for a real service.

RyThM Chatbot 是一个支持中文、日文、英文的多模型 AI 聊天系统。第一版以低成本单机部署为目标，同时包含认证、数据库迁移、流式输出、使用量记录、安全 Cookie、CI 和备份友好的工程结构。

## Features / 功能

- DeepSeek V4 Flash, Gemini 3.1 Flash-Lite and Groq GPT-OSS 20B provider adapters.
- Email registration, verification/resend, password reset and Argon2id password hashes.
- Revocable server-side sessions with Host-only HttpOnly cookies, CSRF and Origin protection.
- Conversation history stored in PostgreSQL; only the latest five complete rounds are sent.
- Server-Sent Events streaming with server-side cancellation, retry boundaries and usage records.
- Chinese, Japanese and English UI with a responsive cyberpunk design.
- Alembic migrations, Docker Compose, health checks, Nginx limits and GitHub Actions CI.

## Architecture / 架构

```text
Browser (React + Vite)
        │ HTTPS / SSE
        ▼
Shared host Nginx :80/:443
        │ Host routing
        ▼
127.0.0.1:8081 (container Nginx)
        │
        ▼
     FastAPI ─────► DeepSeek / Gemini / Groq
        │
        ▼
   PostgreSQL
```

The MVP intentionally uses one server and does not require Redis, Celery or Kubernetes. This is production-oriented, not highly available: a single server failure still causes downtime.

## Quick start / 快速启动

Requirements: Docker Engine with Docker Compose v2.

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```dotenv
POSTGRES_PASSWORD=use-a-long-random-password
DATABASE_URL=postgresql+asyncpg://rythm:use-a-long-random-password@db:5432/rythm_chatbot
DEEPSEEK_API_KEY=your-key
DEEPSEEK_MODEL=your-provider-model-id
```

Then start the complete stack:

```bash
docker compose up --build
```

Open `http://localhost:8081`. Alembic migrations run before the API starts.

In development, when SMTP is empty, verification and reset URLs are written to backend logs. In production, configure SMTP and never expose those tokens in an API response.

## Local development / 本地开发

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

The Vite development server proxies `/api` to `http://localhost:8000`.

## Configuration / 配置

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Async PostgreSQL connection URL |
| `APP_SECRET` | Unique high-entropy key used for keyed Token hashes |
| `TRUSTED_HOSTS` | Accepted HTTP Host names |
| `CSRF_TRUSTED_ORIGINS` | Exact HTTPS origins accepted for state-changing requests |
| `DEEPSEEK_API_KEY` | DeepSeek server-side API key |
| `DEEPSEEK_MODEL` | Explicit DeepSeek provider model ID |
| `GEMINI_API_KEY` | Gemini server-side API key |
| `GEMINI_MODEL` | Explicit Gemini provider model ID |
| `GROQ_API_KEY` | Groq server-side API key |
| `GROQ_MODEL` | Explicit Groq provider model ID |
| `CONTEXT_ROUNDS` | Complete history rounds sent to the provider; default `5` |
| `MAX_OUTPUT_TOKENS` | Global output ceiling; default `512` |
| `DAILY_CHAT_LIMIT` | Accepted generation attempts per verified user per UTC day |
| `MAX_CONCURRENT_GENERATIONS_PER_USER` | Concurrent generation ceiling per user; default `1` |
| `GENERATION_TIMEOUT_SECONDS` | Absolute generation timeout and stale-lock safeguard; default `120` |
| `COOKIE_SECURE` | Must be `true` behind production HTTPS |
| `TURNSTILE_REQUIRED` | Require Cloudflare Turnstile server verification |
| `VITE_TURNSTILE_SITE_KEY` | Public Turnstile site key compiled into the frontend |
| `SMTP_*` | SMTP or Amazon SES SMTP settings |
| `CHATBOT_PORT` | Loopback port exposed to the shared host Nginx; default `8081` |

API keys must never use a `VITE_` prefix. Vite variables are public browser assets.
See `.env.example` for development and `deploy/.env.production.example` for the
complete production contract. The API refuses to start in production when a
required security, mail, database, Turnstile, or Provider setting is unsafe.

## Production checklist / 生产部署检查

- Route `chat.rhythmusic.site` from the shared host Nginx to `127.0.0.1:8081`.
- Terminate TLS in the shared Nginx, redirect HTTP to HTTPS, and enable HSTS.
- Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, correct `FRONTEND_URL` and origins.
- Enable Turnstile and configure SMTP before opening registration publicly.
- Set spending limits in every LLM provider console.
- Back up the PostgreSQL volume daily and test a restore.
- Do not log prompt bodies, session tokens, reset tokens or API keys.
- Restrict database access to the internal Docker network.
- Keep port 8081 bound to loopback and closed in the cloud security group.

The complete t4g.small procedure, shared Nginx vhost, backup timer, restore
procedure, memory limits, and release checks are in [`deploy/README.md`](deploy/README.md).

## Database changes / 数据库扩展

Never edit a migration that has already run in production. Create a new revision:

```bash
cd backend
alembic revision --autogenerate -m "add user avatar"
alembic upgrade head
```

Review autogenerated migrations before execution. For future points or payments, use ledger tables such as `point_accounts` and immutable `point_transactions`; do not treat a single `users.balance` column as the source of truth.

## Validation / 验证

```bash
cd backend && ruff check . && pytest
cd frontend && npm ci && npm test && npm run build
docker compose config
```

## License

No license has been granted yet. Add an explicit license before accepting external contributions or commercial redistribution.
