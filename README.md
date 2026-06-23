# 💎 Transaction & Ranking System

A production-quality financial transaction processing system with a multi-factor ranking algorithm, built with **Python/FastAPI** and a modern **glassmorphism frontend**.

> Built for the Institute of Digital Risk — Backend Engineering Assignment

---

## 🚀 How to Run

### Prerequisites
- **Python 3.10+** installed ([Download](https://www.python.org/downloads/))
- **pip** (comes with Python)

### Quick Start

```bash
# 1. Clone / navigate to the project directory
cd "Institute Of Digital Risk"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Access

| Resource | URL |
|---|---|
| 🌐 **Frontend** | [http://localhost:8000](http://localhost:8000) |
| 📖 **API Docs (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| 📘 **API Docs (ReDoc)** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |

### First Run
1. Open the frontend at `http://localhost:8000`
2. Click **"🌱 Load Demo Data"** to seed 6 users with 25+ realistic transactions
3. Explore the **Transactions**, **User Summary**, and **Ranking** tabs

---

## 📡 API Reference

### 1. `POST /api/transaction` — Create a Transaction

Creates a financial transaction (credit or debit) for a user.

**Request Body:**
```json
{
    "user_id": "user_1",
    "type": "credit",
    "amount": 5000.00,
    "description": "Monthly salary deposit",
    "idempotency_key": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Validation Rules:**
| Field | Rule |
|---|---|
| `user_id` | Required, 1–100 chars, auto-creates user if not found |
| `type` | Required, must be `"credit"` or `"debit"` |
| `amount` | Required, must be > 0 and ≤ 1,000,000 |
| `description` | Optional, max 500 chars |
| `idempotency_key` | Required, 1–200 chars, must be unique per logical transaction |

**Responses:**
| Status | Meaning |
|---|---|
| `201 Created` | Transaction processed successfully |
| `200 OK` | Duplicate idempotency key — cached result returned |
| `400 Bad Request` | Validation error or insufficient balance |
| `422 Unprocessable Entity` | Malformed request body |
| `429 Too Many Requests` | Rate limit exceeded (10/min per user) |

**Example — Successful:**
```bash
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"user_1","type":"credit","amount":5000,"description":"Salary","idempotency_key":"unique-key-123"}'
```

**Example — Duplicate Detection:**
```bash
# Send the SAME request again (same idempotency_key) → returns 200 with cached result
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"user_1","type":"credit","amount":5000,"description":"Salary","idempotency_key":"unique-key-123"}'
```

---

### 2. `GET /api/summary/{user_id}` — User Financial Summary

Returns aggregated financial data for a specific user.

```bash
curl http://localhost:8000/api/summary/user_1
```

**Response:**
```json
{
    "user_id": "user_1",
    "user_name": "Aarav Sharma",
    "total_credits": 72500.00,
    "total_debits": 30000.00,
    "balance": 42500.00,
    "transaction_count": 8,
    "last_transaction_at": "2026-06-23T16:55:00+00:00"
}
```

| Status | Meaning |
|---|---|
| `200 OK` | Summary returned |
| `404 Not Found` | User does not exist |

---

### 3. `GET /api/ranking` — Leaderboard

Returns all users ranked by a multi-factor scoring algorithm.

```bash
curl http://localhost:8000/api/ranking
```

**Response includes:** rank, user info, total score, individual factor scores (volume, frequency, consistency, recency), transaction count, total volume, and balance.

---

## 🏆 Ranking Algorithm

The ranking system uses a **multi-factor weighted scoring model** designed for **fairness** and **manipulation resistance**.

### Formula

```
Score = (0.35 × Volume) + (0.25 × Frequency) + (0.20 × Consistency) + (0.20 × Recency)
```

### Factor Details

| Factor | Weight | How It Works | Anti-Gaming Property |
|---|---|---|---|
| **Volume** | 35% | `log₁₀(1 + total_volume)` normalized to 0–1 | Log scaling: 10× more money ≠ 10× score |
| **Frequency** | 25% | `log₂(1 + txn_count)` normalized to 0–1 | Log scaling: spamming transactions has diminishing returns |
| **Consistency** | 20% | `1 - |credit_ratio - 0.5| × 2` | Penalizes one-sided activity (only deposits = low score) |
| **Recency** | 20% | `2^(-days_since_last / 30)` exponential decay | Inactive accounts naturally decay; no permanent rank hoarding |

### Why This Design is Fair

1. **Log scaling** on volume and frequency prevents whales from dominating and spammers from gaming
2. **Consistency** rewards genuine usage (balanced credits + debits) over artificial inflation
3. **Recency decay** ensures active users rank higher, preventing dormant accounts from holding positions
4. **Combined effect**: To rank #1, a user needs high volume AND high frequency AND balanced usage AND recent activity — gaming just one factor has limited impact

### Example Rankings (with demo data)

| Rank | User | Score | Why |
|---|---|---|---|
| #1 | Aarav Sharma | ~78% | High volume + high frequency + balanced + recent |
| #2 | Priya Patel | ~65% | Very high frequency + balanced, but lower volume |
| #3 | Vikram Singh | ~55% | Moderate all-around |
| #4 | Sneha Gupta | ~40% | High volume but **zero consistency** (all credits) |
| #5 | Rohan Mehta | ~45% | Very high volume but only 2 transactions |
| #6 | Anjali Reddy | ~25% | Single transaction, low everything |

---

## 🔒 Duplicate Request Prevention

### How It Works

Duplicates are prevented via a **client-generated idempotency key** system:

```
Client generates UUID → 
  Sends with request → 
    Server checks DB (UNIQUE constraint) → 
      If exists: return cached 200 → 
      If new: process and store → return 201
```

### Three Layers of Protection

| Layer | Mechanism | Purpose |
|---|---|---|
| **1. DB UNIQUE Constraint** | `idempotency_key TEXT NOT NULL UNIQUE` | Guarantees uniqueness at the storage level |
| **2. Fast Pre-Check** | Query before acquiring write lock | Avoids unnecessary lock contention for duplicates |
| **3. Double-Check Inside Lock** | Re-check after acquiring `asyncio.Lock` | Handles the race condition where two identical requests arrive simultaneously |

### Concurrency Safety

```
Request A (key=abc) ──→ Pre-check (not found) ──→ Acquire lock ──→ Re-check ──→ Insert ──→ Commit
Request B (key=abc) ──→ Pre-check (not found) ──→ Wait for lock ──→ Re-check (found!) ──→ Return cached
```

Even if two identical requests arrive at the exact same millisecond, the double-check pattern inside the write lock ensures only one is processed.

---

## 🛡️ Concurrency & Data Consistency

| Concern | Solution |
|---|---|
| **Concurrent reads** | SQLite WAL (Write-Ahead Logging) mode allows multiple readers |
| **Concurrent writes** | `asyncio.Lock` serializes all write operations |
| **Atomic updates** | Transaction insert + summary update happen in a single SQLite transaction |
| **Balance consistency** | Summary table is updated atomically — never out of sync with transactions |
| **Debit safety** | Balance check happens inside the write lock to prevent overdraft races |
| **Rate limiting** | Sliding window counter: max 10 transactions per user per 60-second window |

---

## 🛡️ Abuse & Manipulation Prevention

| Attack Vector | Defense |
|---|---|
| **Transaction spam** | Rate limiting (10/min per user) + log-scaled frequency scoring |
| **Volume inflation** | Log-scaled volume scoring (10× money ≠ 10× rank) |
| **One-sided credits** | Consistency factor penalizes unbalanced activity |
| **Rank hoarding** | Recency decay (half-life: 30 days) |
| **Replay attacks** | Idempotency key with UNIQUE constraint |
| **Overdraft** | Balance check inside write lock |
| **Invalid inputs** | Pydantic validation: amount caps, type enums, length limits |

---

## 🗃️ Database Schema

Using **SQLite** with WAL mode for simplicity and zero-configuration deployment.

### Tables

```sql
-- Core user registration
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- All financial transactions (idempotency_key is UNIQUE)
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id),
    type TEXT NOT NULL CHECK(type IN ('credit', 'debit')),
    amount REAL NOT NULL CHECK(amount > 0),
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);

-- Materialized aggregates (updated atomically with each transaction)
CREATE TABLE user_summaries (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    total_credits REAL DEFAULT 0,
    total_debits REAL DEFAULT 0,
    balance REAL DEFAULT 0,
    transaction_count INTEGER DEFAULT 0,
    last_transaction_at TEXT
);
```

### Data Flow

```
POST /api/transaction
  → Validate (Pydantic)
  → Rate limit check
  → Idempotency check (fast path)
  → Acquire write lock
  → Re-check idempotency (inside lock)
  → Check user exists (auto-create if needed)
  → Check balance (for debits)
  → BEGIN TRANSACTION
    → INSERT into transactions
    → UPDATE user_summaries (atomic)
  → COMMIT
  → Release lock
  → Return 201
```

---

## 📁 Project Structure

```
Institute Of Digital Risk/
├── backend/
│   ├── __init__.py          # Package marker
│   ├── main.py              # FastAPI app entry point
│   ├── models.py            # Pydantic request/response models
│   ├── database.py          # SQLite async database layer
│   ├── routes.py            # API endpoint definitions
│   ├── ranking.py           # Multi-factor ranking algorithm
│   └── middleware.py         # Rate limiter
├── frontend/
│   ├── index.html           # Single-page application
│   ├── style.css            # Premium dark glassmorphism UI
│   └── app.js               # Client-side logic
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

---

## ⚠️ Assumptions & Limitations

1. **SQLite** is used for simplicity — for production, migrate to PostgreSQL for true concurrent writes
2. **In-memory rate limiter** resets on server restart — use Redis for persistence in production
3. **Users are auto-created** on first transaction — no separate registration flow
4. **Single-process deployment** — the `asyncio.Lock` works within one process; multi-process requires distributed locking
5. **Currency is INR** — hardcoded for the demo; production would support multiple currencies
6. **No authentication** — the system trusts the `user_id` in requests; production would use JWT/OAuth

---

## 🧪 Testing the APIs

### Using cURL

```bash
# Seed demo data
curl -X POST http://localhost:8000/api/seed

# Create a transaction
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","type":"credit","amount":1000,"description":"Test","idempotency_key":"test-key-1"}'

# Get user summary
curl http://localhost:8000/api/summary/test_user

# Get rankings
curl http://localhost:8000/api/ranking

# Test duplicate (same idempotency key — should return 200, not 201)
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","type":"credit","amount":1000,"description":"Test","idempotency_key":"test-key-1"}'

# Test validation error (negative amount)
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","type":"credit","amount":-500,"idempotency_key":"bad-1"}'

# Test missing fields
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user"}'
```

### Using Swagger UI
Visit `http://localhost:8000/docs` for interactive API testing with auto-generated documentation.

---

## 📦 Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI |
| Database | SQLite (WAL mode) via aiosqlite |
| Validation | Pydantic v2 |
| Frontend | Vanilla HTML/CSS/JS |
| Server | Uvicorn (ASGI) |
| API Docs | Swagger UI + ReDoc (auto-generated) |
