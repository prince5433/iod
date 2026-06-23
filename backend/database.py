"""
SQLite database layer with async support.

Design decisions:
- WAL (Write-Ahead Logging) mode for concurrent read access
- Atomic transactions for data consistency
- Materialized user_summaries table updated within the same transaction
  as the insert to guarantee consistency
- UNIQUE constraint on idempotency_key for duplicate prevention at the DB level
"""

import aiosqlite
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

# Database file path
DB_PATH = "transactions.db"

# Lock for serializing write operations to prevent race conditions
_write_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    """Get a database connection with WAL mode enabled."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")
    return db


async def init_db():
    """
    Initialize database schema.
    
    Tables:
    - users: Registered users
    - transactions: All financial transactions with idempotency_key uniqueness
    - user_summaries: Materialized aggregates updated atomically with each transaction
    """
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('credit', 'debit')),
                amount REAL NOT NULL CHECK(amount > 0),
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('completed', 'failed')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS user_summaries (
                user_id TEXT PRIMARY KEY,
                total_credits REAL NOT NULL DEFAULT 0,
                total_debits REAL NOT NULL DEFAULT 0,
                balance REAL NOT NULL DEFAULT 0,
                transaction_count INTEGER NOT NULL DEFAULT 0,
                last_transaction_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_user_id 
                ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_idempotency 
                ON transactions(idempotency_key);
            CREATE INDEX IF NOT EXISTS idx_transactions_created_at 
                ON transactions(created_at);
        """)
        await db.commit()
    finally:
        await db.close()


async def get_user(user_id: str) -> Optional[dict]:
    """Fetch a user by ID. Returns None if not found."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def get_all_users() -> list[dict]:
    """Fetch all registered users."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users ORDER BY created_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def create_user(user_id: str, name: str) -> dict:
    """Create a new user. If user already exists, return existing user."""
    db = await get_db()
    try:
        # Check if user exists
        existing = await get_user(user_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, now)
        )
        # Initialize summary row
        await db.execute(
            "INSERT INTO user_summaries (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()
        return {"id": user_id, "name": name, "created_at": now}
    finally:
        await db.close()


async def check_idempotency(idempotency_key: str) -> Optional[dict]:
    """
    Check if a transaction with this idempotency_key already exists.
    Returns the existing transaction if found, None otherwise.
    
    This is the first line of defense against duplicate processing.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM transactions WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def create_transaction(
    user_id: str,
    txn_type: str,
    amount: float,
    description: str,
    idempotency_key: str
) -> dict:
    """
    Create a new transaction and atomically update the user's summary.
    
    Uses asyncio.Lock to serialize writes and prevent race conditions.
    The transaction insert and summary update happen in a single SQLite
    transaction to guarantee consistency.
    
    Returns the created transaction dict.
    Raises ValueError if user doesn't exist or insufficient balance for debit.
    """
    async with _write_lock:
        db = await get_db()
        try:
            # Re-check idempotency inside the lock (double-check pattern)
            cursor = await db.execute(
                "SELECT * FROM transactions WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            existing = await cursor.fetchone()
            if existing:
                result = dict(existing)
                result["is_duplicate"] = True
                return result

            # Verify user exists
            cursor = await db.execute(
                "SELECT id FROM users WHERE id = ?", (user_id,)
            )
            if not await cursor.fetchone():
                raise ValueError(f"User '{user_id}' not found. Please create the user first.")

            # For debits, check sufficient balance
            if txn_type == "debit":
                cursor = await db.execute(
                    "SELECT balance FROM user_summaries WHERE user_id = ?",
                    (user_id,)
                )
                summary_row = await cursor.fetchone()
                current_balance = summary_row["balance"] if summary_row else 0
                if current_balance < amount:
                    raise ValueError(
                        f"Insufficient balance. Current: {current_balance:.2f}, "
                        f"Requested debit: {amount:.2f}"
                    )

            # Generate transaction ID and timestamp
            txn_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            # === ATOMIC: Insert transaction + Update summary ===
            await db.execute(
                """INSERT INTO transactions 
                   (id, idempotency_key, user_id, type, amount, description, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)""",
                (txn_id, idempotency_key, user_id, txn_type, amount, description, now)
            )

            # Update materialized summary atomically
            if txn_type == "credit":
                await db.execute(
                    """UPDATE user_summaries SET
                       total_credits = total_credits + ?,
                       balance = balance + ?,
                       transaction_count = transaction_count + 1,
                       last_transaction_at = ?
                       WHERE user_id = ?""",
                    (amount, amount, now, user_id)
                )
            else:  # debit
                await db.execute(
                    """UPDATE user_summaries SET
                       total_debits = total_debits + ?,
                       balance = balance - ?,
                       transaction_count = transaction_count + 1,
                       last_transaction_at = ?
                       WHERE user_id = ?""",
                    (amount, amount, now, user_id)
                )

            await db.commit()

            return {
                "id": txn_id,
                "user_id": user_id,
                "type": txn_type,
                "amount": amount,
                "description": description,
                "idempotency_key": idempotency_key,
                "status": "completed",
                "created_at": now,
                "is_duplicate": False
            }

        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()


async def get_user_summary(user_id: str) -> Optional[dict]:
    """
    Get aggregated financial summary for a user.
    Reads from the materialized user_summaries table for consistency.
    """
    db = await get_db()
    try:
        # Get user info
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        user = await cursor.fetchone()
        if not user:
            return None

        # Get summary
        cursor = await db.execute(
            "SELECT * FROM user_summaries WHERE user_id = ?", (user_id,)
        )
        summary = await cursor.fetchone()

        if summary:
            return {
                "user_id": user["id"],
                "user_name": user["name"],
                "total_credits": round(summary["total_credits"], 2),
                "total_debits": round(summary["total_debits"], 2),
                "balance": round(summary["balance"], 2),
                "transaction_count": summary["transaction_count"],
                "last_transaction_at": summary["last_transaction_at"]
            }
        else:
            return {
                "user_id": user["id"],
                "user_name": user["name"],
                "total_credits": 0.0,
                "total_debits": 0.0,
                "balance": 0.0,
                "transaction_count": 0,
                "last_transaction_at": None
            }
    finally:
        await db.close()


async def get_all_summaries() -> list[dict]:
    """
    Get summaries for all users. Used by the ranking engine.
    Only returns users with at least one transaction.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT u.id as user_id, u.name as user_name,
                      s.total_credits, s.total_debits, s.balance,
                      s.transaction_count, s.last_transaction_at
               FROM users u
               JOIN user_summaries s ON u.id = s.user_id
               WHERE s.transaction_count > 0
               ORDER BY s.transaction_count DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def seed_demo_data():
    """
    Seed the database with realistic demo data for demonstration purposes.
    
    Creates 6 users with varied transaction patterns to showcase
    the ranking algorithm's fairness properties:
    - High-volume balanced user
    - Frequent small transactions
    - Infrequent large transactions  
    - Credit-heavy user (penalized by consistency factor)
    - Recent active user
    - Dormant user (penalized by recency factor)
    """
    import random

    demo_users = [
        ("user_1", "Aarav Sharma"),
        ("user_2", "Priya Patel"),
        ("user_3", "Rohan Mehta"),
        ("user_4", "Sneha Gupta"),
        ("user_5", "Vikram Singh"),
        ("user_6", "Anjali Reddy"),
    ]

    demo_transactions = [
        # User 1: High-volume, balanced (credits and debits)
        ("user_1", "credit", 50000.00, "Salary deposit"),
        ("user_1", "debit", 15000.00, "Rent payment"),
        ("user_1", "credit", 12000.00, "Freelance income"),
        ("user_1", "debit", 8000.00, "Insurance premium"),
        ("user_1", "debit", 5000.00, "Groceries"),
        ("user_1", "credit", 3000.00, "Cashback reward"),
        ("user_1", "debit", 2000.00, "Utilities"),
        ("user_1", "credit", 7500.00, "Investment returns"),

        # User 2: Frequent small transactions
        ("user_2", "credit", 2000.00, "Daily earnings"),
        ("user_2", "debit", 500.00, "Coffee subscription"),
        ("user_2", "credit", 1500.00, "Side income"),
        ("user_2", "debit", 800.00, "Transport"),
        ("user_2", "credit", 1000.00, "Refund"),
        ("user_2", "debit", 300.00, "Snacks"),
        ("user_2", "credit", 2500.00, "Bonus"),
        ("user_2", "debit", 1200.00, "Shopping"),
        ("user_2", "credit", 900.00, "Gift received"),
        ("user_2", "debit", 600.00, "Mobile recharge"),

        # User 3: Infrequent, large transactions
        ("user_3", "credit", 200000.00, "Property sale"),
        ("user_3", "debit", 150000.00, "Car purchase"),

        # User 4: Credit-heavy (one-sided — should be penalized)
        ("user_4", "credit", 30000.00, "Deposit 1"),
        ("user_4", "credit", 25000.00, "Deposit 2"),
        ("user_4", "credit", 20000.00, "Deposit 3"),
        ("user_4", "credit", 15000.00, "Deposit 4"),

        # User 5: Recent, moderately active
        ("user_5", "credit", 10000.00, "Salary"),
        ("user_5", "debit", 4000.00, "Rent"),
        ("user_5", "credit", 5000.00, "Bonus"),
        ("user_5", "debit", 2000.00, "Bills"),

        # User 6: Single old transaction (dormant — penalized by recency)
        ("user_6", "credit", 5000.00, "Initial deposit"),
    ]

    users_created = 0
    txns_created = 0

    for user_id, name in demo_users:
        await create_user(user_id, name)
        users_created += 1

    for user_id, txn_type, amount, description in demo_transactions:
        idem_key = f"seed_{user_id}_{txn_type}_{amount}_{description.replace(' ', '_')}"
        try:
            existing = await check_idempotency(idem_key)
            if not existing:
                await create_transaction(user_id, txn_type, amount, description, idem_key)
                txns_created += 1
        except ValueError:
            pass  # Skip if insufficient balance etc.

    return users_created, txns_created
