"""
Pydantic models for request validation and response serialization.

All models enforce strict validation rules:
- Amounts must be positive and capped at 1,000,000
- Transaction types are restricted to 'credit' or 'debit'
- Idempotency keys are required and validated as non-empty strings
- User IDs must be non-empty strings
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class TransactionType(str, Enum):
    """Allowed transaction types."""
    CREDIT = "credit"
    DEBIT = "debit"


# ─── Request Models ───────────────────────────────────────────────

class TransactionRequest(BaseModel):
    """
    Request body for POST /api/transaction.
    
    Requires a client-generated idempotency_key (UUID v4 recommended)
    to prevent duplicate processing of the same logical transaction.
    """
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique identifier of the user",
        examples=["user_1"]
    )
    type: TransactionType = Field(
        ...,
        description="Transaction type: 'credit' (money in) or 'debit' (money out)",
        examples=["credit"]
    )
    amount: float = Field(
        ...,
        gt=0,
        le=1_000_000,
        description="Transaction amount (must be > 0 and ≤ 1,000,000)",
        examples=[500.00]
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Optional description of the transaction",
        examples=["Monthly salary deposit"]
    )
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Client-generated unique key to prevent duplicate processing (use UUID v4)",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Strip whitespace and ensure user_id is not blank."""
        v = v.strip()
        if not v:
            raise ValueError("user_id cannot be blank")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount_precision(cls, v: float) -> float:
        """Round to 2 decimal places to avoid floating-point issues."""
        return round(v, 2)

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v: str) -> str:
        """Strip whitespace and ensure idempotency_key is not blank."""
        v = v.strip()
        if not v:
            raise ValueError("idempotency_key cannot be blank")
        return v


# ─── Response Models ──────────────────────────────────────────────

class TransactionResponse(BaseModel):
    """Response for a successful transaction."""
    id: str
    user_id: str
    type: TransactionType
    amount: float
    description: str
    idempotency_key: str
    status: str
    created_at: str
    is_duplicate: bool = Field(
        default=False,
        description="True if this response is a cached result from a previous identical request"
    )


class UserSummaryResponse(BaseModel):
    """Aggregated financial summary for a single user."""
    user_id: str
    user_name: str
    total_credits: float
    total_debits: float
    balance: float
    transaction_count: int
    last_transaction_at: Optional[str] = None


class RankingFactors(BaseModel):
    """Breakdown of individual ranking factor scores."""
    volume_score: float
    frequency_score: float
    consistency_score: float
    recency_score: float


class RankingEntry(BaseModel):
    """A single entry in the ranking leaderboard."""
    rank: int
    user_id: str
    user_name: str
    total_score: float
    factors: RankingFactors
    transaction_count: int
    total_volume: float
    balance: float


class RankingResponse(BaseModel):
    """Response for GET /api/ranking."""
    rankings: list[RankingEntry]
    total_users: int
    algorithm: str = "Multi-factor weighted scoring (Volume 35%, Frequency 25%, Consistency 20%, Recency 20%)"
    last_updated: str


class UserListResponse(BaseModel):
    """Response for GET /api/users."""
    users: list[dict]
    total: int


class ErrorResponse(BaseModel):
    """Standardized error response."""
    error: str
    detail: str
    status_code: int


class SeedResponse(BaseModel):
    """Response for POST /api/seed."""
    message: str
    users_created: int
    transactions_created: int
