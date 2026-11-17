# Production Deployment & Free-Tier Hosting Guide (Phase 7)

This guide documents the end-to-end production architecture, zero-cost / free-tier cloud deployment steps, environment variable configuration, and post-deployment smoke verification for the SHG Credit Manager.

---

## 1. Cloud Architecture & Free-Tier Options

The system consists of 4 components designed for zero-cost deployment on modern cloud platforms:

| Component | Recommended Free-Tier Provider | Alternative Providers | Free Tier Quota |
|---|---|---|---|
| **Relational Database** (PostgreSQL 16) | **Neon.tech** | Supabase, Render Postgres | 0.5 GB storage, autoscaling compute, pooled connections |
| **Async Broker** (Redis 7) | **Upstash Redis** | Render Redis, Railway | 10,000 commands/day, serverless persistence |
| **API & Outbox Worker** (FastAPI / ARQ) | **Render.com** (Web Service + Background Worker) | Railway, Fly.io, Koyeb | 512 MB RAM, 0.1 CPU, automatic HTTPS, free subdomains |
| **Frontend SPA** (Vite + React 18) | **Vercel** | Netlify, Cloudflare Pages, Render Static | 100 GB bandwidth, global edge CDN, automatic SSL |

---

## 2. Environment Variables Reference

### 2.1 Backend (`/backend/.env`)

| Variable | Required | Default / Example Value | Description |
|---|---|---|---|
| `ENVIRONMENT` | Yes | `production` (or `development`) | Runtime environment mode |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@ep-cool-db.neon.tech/neondb?ssl=require` | Async PostgreSQL connection string |
| `REDIS_URL` | Yes | `rediss://default:token@cool-redis.upstash.io:6379` | Redis connection URL for outbox worker |
| `SECRET_KEY` | Yes | `min-32-chars-cryptographically-secure-random-string` | JWT token signing key (`openssl rand -hex 32`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| No | `15` | JWT access token lifespan |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifespan |
| `CORS_ORIGINS` | Yes | `["https://shg-credit.vercel.app"]` | Allowed frontend origins (JSON array or comma-separated) |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `GEMINI_API_KEY` | Optional | `AIzaSy...` | Google Gemini API key for Assistant & Draft-from-notes |

### 2.2 Frontend (`/frontend/.env.production`)

| Variable | Required | Default / Example Value | Description |
|---|---|---|---|
| `VITE_API_URL` | Yes | `https://shg-backend.onrender.com` | Base URL of deployed FastAPI backend |

---

## 3. Step-by-Step Deployment Instructions

### Step 1: Provision Managed Database (Neon.tech)
1. Sign up at [neon.tech](https://neon.tech) and create a new project named `shg-credit-manager`.
2. Select PostgreSQL 16 in your nearest cloud region (e.g., `ap-southeast-1` or `eu-central-1`).
3. Copy the pooled connection string, ensuring the protocol prefix is `postgresql+asyncpg://` for SQLAlchemy:
   ```bash
   postgresql+asyncpg://[user]:[password]@[endpoint].neon.tech/neondb?ssl=require
   ```

### Step 2: Provision Serverless Redis (Upstash)
1. Sign up at [upstash.com](https://upstash.com) and create a Redis database.
2. Select your nearest region and copy the `rediss://` connection URL.

### Step 3: Deploy Backend on Render.com
1. Connect your GitHub repository to [render.com](https://render.com).
2. Create a new **Web Service**:
   - **Name**: `shg-credit-backend`
   - **Environment**: `Docker` (or Python 3.12)
   - **Dockerfile Path**: `./backend/Dockerfile`
   - **Plan**: `Free`
   - **Health Check Path**: `/health`
3. In **Environment Variables**, add:
   - `ENVIRONMENT=production`
   - `DATABASE_URL=<your-neon-asyncpg-url>`
   - `REDIS_URL=<your-upstash-redis-url>`
   - `SECRET_KEY=<generate-via-openssl-rand-hex-32>`
   - `CORS_ORIGINS=["https://shg-credit.vercel.app","http://localhost:3000"]`
   - `GEMINI_API_KEY=<optional-gemini-key>`
4. Click **Create Web Service**. Render will build the multi-stage Docker image and deploy it.

### Step 4: Run Migrations and Realistic Seed Data
Using Render Shell, GitHub Actions, or local CLI pointing to the production database:
```bash
# 1. Apply double-entry database schema migrations
alembic -c backend/alembic.ini upgrade head

# 2. Seed realistic data (SPEC Section 16: 2 SHGs, 6 months meetings, loans in all states, 1 reversal)
python -m backend.app.scripts.seed
```

### Step 5: Deploy Frontend on Vercel
1. Sign up at [vercel.com](https://vercel.com) and import your Git repository.
2. Configure Project:
   - **Root Directory**: `frontend`
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. In **Environment Variables**, add:
   - `VITE_API_URL=https://shg-credit-backend.onrender.com`
4. Click **Deploy**. Vercel will build the SPA and distribute it globally over CDN with automatic SSL.

---

## 4. Post-Deployment Smoke Verification

Verify that your live deployment is healthy, authenticated, and responsive by running the automated smoke verification script:

```bash
# Verify live deployment
python scripts/smoke_test.py --url https://shg-credit-backend.onrender.com --email admin@shg.org --password AdminPass123!
```

### Expected Output:
```text
================================================================================
SHG Credit Manager: Production Smoke Verification -> https://shg-credit-backend.onrender.com
================================================================================

1. Testing GET /health...
   [PASS] /health responded 200 OK in 84.2ms

2. Testing GET /ready (database connectivity)...
   [PASS] /ready responded 200 OK (DB connected) in 112.5ms

3. Testing GET /metrics (observability exporter)...
   [PASS] /metrics exported Prometheus telemetry in 95.1ms

4. Testing Authentication POST /api/v1/auth/login...
   [PASS] Authenticated successfully in 160.3ms

5. Testing Authenticated Read: GET /api/v1/dashboard...
   [PASS] Dashboard loaded in 145.8ms

================================================================================
[SUCCESS] All smoke tests passed! Production deployment is healthy.
================================================================================
```

---

## 5. Local Docker-Compose Run

To run the entire distributed production stack locally with Prometheus and Grafana:

```bash
# Start all 6 services (Postgres, Redis, Backend, Outbox Worker, Frontend, Prometheus, Grafana)
docker compose up --build -d

# Check service health
docker compose ps

# Access applications:
# Frontend SPA:       http://localhost:3000
# Backend API & Docs: http://localhost:8000/docs
# Prometheus:         http://localhost:9090
# Grafana Dashboard:  http://localhost:3001 (admin / admin)
```
