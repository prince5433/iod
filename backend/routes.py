"""
API route definitions.

Endpoints:
  POST /api/transaction     — Create a financial transaction
  GET  /api/summary/{uid}   — Get aggregated summary for a user
  GET  /api/ranking          — Get ranked leaderboard
  GET  /api/users            — List all registered users
  POST /api/seed             — Seed demo data for demonstration
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from .models import (
    TransactionRequest, TransactionResponse,
    UserSummaryResponse, RankingResponse, RankingEntry, RankingFactors,
    UserListResponse, SeedResponse, ErrorResponse,
)
from .database import (
    check_idempotency, create_transaction, get_user_summary,
    get_all_summaries, get_all_users, seed_demo_data, get_user, create_user,
)
from .ranking import compute_rankings
from .middleware import rate_limiter

router = APIRouter(prefix="/api")


# ─── POST /api/transaction ────────────────────────────────────────

@router.post(
    "/transaction",
    response_model=TransactionResponse,
    status_code=201,
    responses={
        200: {"model": TransactionResponse, "description": "Duplicate request — cached result returned"},
        400: {"model": ErrorResponse, "description": "Validation error or insufficient balance"},
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Create a financial transaction",
    description=(
        "Process a credit or debit transaction for a user. "
        "Requires an idempotency_key to prevent duplicate processing. "
        "If the same idempotency_key is sent again, the original result is returned."
    ),
)
async def post_transaction(txn: TransactionRequest):
    """
    Create a new transaction with full validation and safety checks:
    
    1. Rate limiting — max 10 requests per user per minute
    2. Idempotency check — return cached result for duplicate keys
    3. User existence check — auto-create if not found
    4. Balance check — reject debits exceeding available balance
    5. Atomic insert + summary update
    """
    # Step 1: Rate limit check
    allowed, retry_after = rate_limiter.is_allowed(txn.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max 10 transactions per minute. Retry after {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    # Step 2: Fast idempotency check (before acquiring write lock)
    existing = await check_idempotency(txn.idempotency_key)
    if existing:
        return JSONResponse(
            status_code=200,
            content={
                **existing,
                "is_duplicate": True,
            },
        )

    # Step 3: Auto-create user if they don't exist
    user = await get_user(txn.user_id)
    if not user:
        # Auto-create with a generated name
        await create_user(txn.user_id, f"User {txn.user_id}")

    # Step 4 & 5: Create transaction (includes balance check + atomic update)
    try:
        result = await create_transaction(
            user_id=txn.user_id,
            txn_type=txn.type.value,
            amount=txn.amount,
            description=txn.description,
            idempotency_key=txn.idempotency_key,
        )

        # Handle duplicate detected inside the lock
        if result.get("is_duplicate"):
            return JSONResponse(
                status_code=200,
                content={**result, "is_duplicate": True},
            )

        return JSONResponse(status_code=201, content=result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── GET /api/summary/{user_id} ──────────────────────────────────

@router.get(
    "/summary/{user_id}",
    response_model=UserSummaryResponse,
    responses={
        404: {"model": ErrorResponse, "description": "User not found"},
    },
    summary="Get user financial summary",
    description="Returns aggregated financial data for a specific user.",
)
async def get_summary(user_id: str):
    """
    Get financial summary for a user including:
    - Total credits and debits
    - Current balance
    - Transaction count
    - Last transaction timestamp
    """
    user_id = user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id cannot be empty")

    summary = await get_user_summary(user_id)
    if not summary:
        raise HTTPException(
            status_code=404,
            detail=f"User '{user_id}' not found",
        )

    return summary


# ─── GET /api/ranking ─────────────────────────────────────────────

@router.get(
    "/ranking",
    response_model=RankingResponse,
    summary="Get user rankings",
    description=(
        "Returns a ranked leaderboard of all users based on a multi-factor "
        "scoring algorithm: Volume (35%), Frequency (25%), Consistency (20%), Recency (20%)."
    ),
)
async def get_ranking():
    """
    Compute and return the ranking leaderboard.
    
    Rankings are computed on-demand from materialized summaries,
    ensuring they always reflect the latest data.
    """
    summaries = await get_all_summaries()
    ranked = compute_rankings(summaries)

    ranking_entries = [
        RankingEntry(
            rank=entry["rank"],
            user_id=entry["user_id"],
            user_name=entry["user_name"],
            total_score=entry["total_score"],
            factors=RankingFactors(**entry["factors"]),
            transaction_count=entry["transaction_count"],
            total_volume=entry["total_volume"],
            balance=entry["balance"],
        )
        for entry in ranked
    ]

    return RankingResponse(
        rankings=ranking_entries,
        total_users=len(ranking_entries),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


# ─── GET /api/users ──────────────────────────────────────────────

@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users",
    description="Returns a list of all registered users.",
)
async def list_users():
    """List all registered users."""
    users = await get_all_users()
    return UserListResponse(users=users, total=len(users))


# ─── POST /api/seed ──────────────────────────────────────────────

@router.post(
    "/seed",
    response_model=SeedResponse,
    summary="Seed demo data",
    description="Populate the database with realistic demo data for testing. Safe to call multiple times (idempotent).",
)
async def seed_data():
    """
    Seed the database with demo users and transactions.
    Uses idempotency keys internally so it's safe to call repeatedly.
    """
    users_created, txns_created = await seed_demo_data()
    return SeedResponse(
        message="Demo data seeded successfully" if txns_created > 0 else "Demo data already exists",
        users_created=users_created,
        transactions_created=txns_created,
    )
