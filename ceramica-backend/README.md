# Ceramica Store — Backend API

Multi-tenant ceramic store management system built as a production-ready backend that serves Android, iOS, Desktop, and Web clients via REST + WebSocket.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Backend                   │
│         REST API + WebSocket (/ws/{store_id})       │
├─────────┬──────────┬──────────┬──────────┬──────────┤
│ Android │   iOS    │ Desktop  │   Web    │   TUI    │
│(Flutter)│(Flutter) │(Electron)│ (React)  │  (Rich)  │
└─────────┴──────────┴──────────┴──────────┴──────────┘
```

### Tech Stack
| Layer | Technology |
|---|---|
| API | FastAPI + uvicorn (ASGI) |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| DB (dev) | SQLite + aiosqlite |
| DB (prod) | PostgreSQL + asyncpg |
| Cache/PubSub | Redis (Upstash in prod) |
| Auth | JWT (python-jose) + bcrypt |
| Background | Celery |
| Validation | Pydantic v2 |

---

## Quick Start (Local — No Docker)

```bash
cd ceramica-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # uses SQLite by default

# Start API (auto-creates SQLite tables on first run)
uvicorn main:app --reload

# Seed with demo data
python -m scripts.seed

# Open Swagger UI
open http://localhost:8000/docs

# Launch TUI client
python cli/main.py
```

Demo credentials after seed:
- **Admin**: `admin@ceramica.demo` / `Admin1234!` — store slug: `ceramica-san-martin`
- **Cashier**: `cajero@ceramica.demo` / `Cajero123!`

---

## Quick Start (Docker)

```bash
cd ceramica-backend
cp .env.example .env
# Edit .env → set DATABASE_URL to postgresql+asyncpg://ceramica:ceramica@db:5432/ceramica_db

docker-compose up -d
docker-compose exec api alembic upgrade head
docker-compose exec api python -m scripts.seed
```

---

## Running Tests

```bash
pytest -v --cov=. --cov-report=term-missing
```

---

## API Overview

All responses use the envelope:
```json
{ "data": <payload>, "error": null, "meta": { ... } }
```

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register-store` | Onboard new store + owner |
| POST | `/auth/login` | Returns JWT access + refresh tokens |
| POST | `/auth/refresh` | Rotate refresh token |
| POST | `/auth/logout` | Revoke refresh token |
| GET | `/auth/me` | Current user info |

### Products / Inventory
| Method | Endpoint | Description |
|---|---|---|
| GET | `/products` | List with filters, pagination |
| POST | `/products` | Create product |
| GET | `/products/{id}` | Get single product |
| PUT | `/products/{id}` | Update product |
| DELETE | `/products/{id}` | Soft delete |
| GET | `/products/low-stock` | Products at or below threshold |
| POST | `/products/{id}/adjust-stock` | Manual correction with reason |

### Sales
| Method | Endpoint | Description |
|---|---|---|
| GET | `/sales` | List (paginated) |
| POST | `/sales` | Create sale + decrement stock + broadcast WS |
| GET | `/sales/{id}` | Get with items + payments |
| PATCH | `/sales/{id}/status` | Update status |
| POST | `/sales/{id}/payment` | Partial or full payment |

### Clients
| Method | Endpoint | Description |
|---|---|---|
| GET | `/clients` | List with search |
| POST | `/clients` | Create |
| GET | `/clients/{id}` | Get |
| PUT | `/clients/{id}` | Update |
| GET | `/clients/{id}/debt` | Debt summary + pending sales |
| POST | `/clients/{id}/payment` | Apply payment to oldest unpaid sale |
| GET | `/clients/{id}/history` | Sales history |

### Suppliers
| Method | Endpoint | Description |
|---|---|---|
| GET | `/suppliers` | List |
| POST | `/suppliers` | Create |
| POST | `/suppliers/purchase-orders` | Create purchase order |
| GET | `/suppliers/purchase-orders` | List orders |
| PATCH | `/suppliers/purchase-orders/{id}/receive` | Receive stock + broadcast WS |

### Finance
| Method | Endpoint | Description |
|---|---|---|
| GET | `/finance/dashboard` | Real-time P&L summary |
| POST | `/finance/expense` | Record expense |
| GET | `/finance/expenses` | List expenses |
| GET | `/finance/cashflow` | Cash flow by date range |
| GET | `/finance/reports/sales` | Sales report |
| GET | `/finance/reports/inventory-valuation` | Stock valuation |

---

## WebSocket

Connect to `ws://host/ws/{store_id}?token=<access_token>`

Events broadcast to all clients of a store:

| Event | Trigger |
|---|---|
| `sale_created` | New sale finalized |
| `payment_received` | Payment applied to a sale |
| `stock_updated` | Manual stock adjustment |
| `low_stock_alert` | Product falls at/below threshold |
| `purchase_received` | Purchase order partially/fully received |

Message format:
```json
{ "type": "sale_created", "payload": { "sale_id": "...", "total_cents": 5000, "status": "completed" } }
```

Send `"ping"` → receives `"pong"` to keep connection alive.

---

## Database Design Decisions

| Decision | Rationale |
|---|---|
| UUID primary keys | Required for distributed/offline-first systems — no coordination needed |
| Integer cents (not float) | Float arithmetic is lossy; `$0.10 + $0.20 ≠ $0.30` in IEEE 754 |
| `is_active` soft delete | Preserves referential integrity in audit trails |
| `store_id` on every table | Multi-tenant isolation — enforced at middleware level |
| `version` on Product | Optimistic locking prevents concurrent stock race conditions |
| `client_generated_id` | Idempotency for offline-first: safe to retry any operation |
| Immutable `AuditLog` | Full who/what/when for compliance; never soft-deleted |

---

## Offline-First Strategy

Mobile clients can operate without connectivity:

1. **Queue operations locally** — each operation gets a UUID `client_generated_id` before being sent
2. **Retry safely** — server deduplicates by `client_generated_id` (idempotent endpoints)
3. **Conflict resolution** — last-write-wins using server UTC timestamp as tiebreaker
4. **Sync on reconnect** — client replays queued operations; duplicates are silently ignored

---

## Multi-Tenant Isolation

- Every DB record has `store_id` FK
- JWT access token contains `store_id` claim
- `get_store_id` dependency extracts `store_id` from authenticated user
- All service queries are scoped to `store_id` — cross-tenant data leakage is structurally impossible

---

## Deployment: Supabase + Railway/Render

### 1. Database (Supabase Free Tier — 500MB)

1. Create project at [supabase.com](https://supabase.com)
2. Copy the connection string from **Settings → Database → Connection String → URI**
3. Use `postgresql+asyncpg://...` scheme (replace `postgresql://` prefix)

### 2. Redis (Upstash Free Tier)

1. Create database at [upstash.com](https://upstash.com)
2. Copy the `rediss://` TLS connection URL

### 3. Deploy API (Railway)

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
```

Set environment variables in Railway dashboard:
```
DATABASE_URL=postgresql+asyncpg://postgres:[password]@db.[ref].supabase.co:5432/postgres
REDIS_URL=rediss://default:[password]@[endpoint].upstash.io:6380
SECRET_KEY=<generate with: openssl rand -hex 32>
ENVIRONMENT=production
CORS_ORIGINS=https://your-frontend.com
```

Run migrations:
```bash
railway run alembic upgrade head
```

### 4. Deploy API (Render)

1. Connect GitHub repo
2. Set **Build Command**: `pip install -r requirements.txt`
3. Set **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add the same environment variables above

---

## Project Structure

```
ceramica-backend/
├── main.py                    # FastAPI app, lifespan, routers, CORS
├── config.py                  # Pydantic Settings from .env
├── database.py                # Async SQLAlchemy engine + session
├── websocket_manager.py       # Connection manager + Redis pub/sub
├── models/
│   ├── base_mixin.py          # UUID, timestamps, soft-delete, store_id mixins
│   ├── store.py               # Store (tenant root)
│   ├── user.py                # User, RefreshToken
│   ├── product.py             # Product (with version for optimistic locking)
│   ├── client.py              # Client
│   ├── sale.py                # Sale, SaleItem, Payment
│   ├── supplier.py            # Supplier, PurchaseOrder, PurchaseOrderItem
│   ├── finance.py             # Expense
│   └── audit.py               # AuditLog (immutable)
├── schemas/                   # Pydantic v2 request/response schemas
├── routers/                   # FastAPI routers (one per domain)
├── services/                  # Business logic (stock validation, P&L, etc.)
├── dependencies/              # Auth, DB session, store context
├── background_tasks/          # Celery app + tasks
├── cli/                       # Rich TUI (Client #1)
├── alembic/                   # Migrations
├── scripts/seed.py            # Demo data
├── tests/                     # pytest-asyncio test suite
├── docker-compose.yml         # PostgreSQL + Redis + API + Worker
├── Dockerfile
└── .env.example
```
