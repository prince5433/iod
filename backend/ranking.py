"""
Multi-factor ranking algorithm.

Computes a composite score for each user based on 4 weighted factors:
  Score = (0.35 × Volume) + (0.25 × Frequency) + (0.20 × Consistency) + (0.20 × Recency)

Anti-manipulation design:
  - Log scaling on volume and frequency prevents linear gaming
    (spending 10x more does NOT give 10x the score)
  - Consistency factor penalizes one-sided activity (all credits, no debits)
    which discourages artificial inflation
  - Recency factor decays over time so dormant accounts lose rank
  - Combined with rate limiting and amount caps from the API layer
"""

import math
from datetime import datetime, timezone
from typing import Optional


# ─── Configuration ────────────────────────────────────────────────

WEIGHTS = {
    "volume": 0.35,
    "frequency": 0.25,
    "consistency": 0.20,
    "recency": 0.20,
}

# Recency decay: score halves every RECENCY_HALF_LIFE_DAYS days
RECENCY_HALF_LIFE_DAYS = 30


# ─── Factor Computations ─────────────────────────────────────────

def compute_volume_score(total_credits: float, total_debits: float) -> float:
    """
    Score based on total transaction volume (credits + debits).
    Uses log10 scaling to dampen the advantage of very large volumes.
    
    Examples:
      Volume ₹1,000   → score ~3.0
      Volume ₹10,000  → score ~4.0
      Volume ₹100,000 → score ~5.0  (only 67% more than ₹1,000)
    """
    total_volume = total_credits + total_debits
    if total_volume <= 0:
        return 0.0
    return math.log10(1 + total_volume)


def compute_frequency_score(transaction_count: int) -> float:
    """
    Score based on number of transactions.
    Uses log2 scaling — diminishing returns for spamming transactions.
    
    Examples:
      4 transactions  → score ~2.3
      16 transactions → score ~4.1
      64 transactions → score ~6.0  (only 2.6x more than 4 txns)
    """
    if transaction_count <= 0:
        return 0.0
    return math.log2(1 + transaction_count)


def compute_consistency_score(total_credits: float, total_debits: float) -> float:
    """
    Score based on how balanced the user's credits and debits are.
    
    A user who only credits (or only debits) gets a low score.
    A perfectly balanced user (50/50 split) gets the maximum score of 1.0.
    
    Formula: 1 - |credits_ratio - 0.5| * 2
    This maps: 50/50 → 1.0, 100/0 → 0.0, 0/100 → 0.0
    
    This prevents gaming by just depositing money without real usage.
    """
    total = total_credits + total_debits
    if total <= 0:
        return 0.0
    
    credit_ratio = total_credits / total
    # Distance from perfect balance (0.5)
    imbalance = abs(credit_ratio - 0.5)
    # Map: 0 imbalance → 1.0 score, 0.5 imbalance → 0.0 score
    return max(0.0, 1.0 - (imbalance * 2))


def compute_recency_score(last_transaction_at: Optional[str]) -> float:
    """
    Score based on how recently the user transacted.
    Uses exponential decay with a configurable half-life.
    
    Score = 2^(-days_since_last / half_life)
    
    Examples (with 30-day half-life):
      Today        → 1.0
      30 days ago  → 0.5
      60 days ago  → 0.25
      90 days ago  → 0.125
    """
    if not last_transaction_at:
        return 0.0
    
    try:
        last_txn = datetime.fromisoformat(last_transaction_at)
        if last_txn.tzinfo is None:
            last_txn = last_txn.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        days_since = max(0, (now - last_txn).total_seconds() / 86400)
        
        # Exponential decay
        return math.pow(2, -days_since / RECENCY_HALF_LIFE_DAYS)
    except (ValueError, TypeError):
        return 0.0


# ─── Composite Score ──────────────────────────────────────────────

def compute_ranking_score(user_summary: dict) -> dict:
    """
    Compute the composite ranking score for a user.
    
    Args:
        user_summary: dict with keys:
            total_credits, total_debits, transaction_count, last_transaction_at
    
    Returns:
        dict with individual factor scores and the weighted total.
    """
    volume = compute_volume_score(
        user_summary["total_credits"],
        user_summary["total_debits"]
    )
    frequency = compute_frequency_score(
        user_summary["transaction_count"]
    )
    consistency = compute_consistency_score(
        user_summary["total_credits"],
        user_summary["total_debits"]
    )
    recency = compute_recency_score(
        user_summary.get("last_transaction_at")
    )

    # Normalize volume and frequency to 0-1 range for fair weighting
    # Using soft caps based on expected maximums
    volume_normalized = min(1.0, volume / 7.0)       # log10(10M) ≈ 7
    frequency_normalized = min(1.0, frequency / 7.0)  # log2(128) ≈ 7

    total_score = (
        WEIGHTS["volume"] * volume_normalized +
        WEIGHTS["frequency"] * frequency_normalized +
        WEIGHTS["consistency"] * consistency +
        WEIGHTS["recency"] * recency
    )

    return {
        "volume_score": round(volume_normalized, 4),
        "frequency_score": round(frequency_normalized, 4),
        "consistency_score": round(consistency, 4),
        "recency_score": round(recency, 4),
        "total_score": round(total_score, 4),
    }


def compute_rankings(user_summaries: list[dict]) -> list[dict]:
    """
    Compute rankings for all users and sort by total score descending.
    Ties are broken by transaction count, then by total volume.
    
    Args:
        user_summaries: list of user summary dicts from the database
    
    Returns:
        Sorted list of ranking entries with rank, scores, and metadata.
    """
    rankings = []
    
    for summary in user_summaries:
        scores = compute_ranking_score(summary)
        total_volume = summary["total_credits"] + summary["total_debits"]
        
        rankings.append({
            "user_id": summary["user_id"],
            "user_name": summary["user_name"],
            "total_score": scores["total_score"],
            "factors": {
                "volume_score": scores["volume_score"],
                "frequency_score": scores["frequency_score"],
                "consistency_score": scores["consistency_score"],
                "recency_score": scores["recency_score"],
            },
            "transaction_count": summary["transaction_count"],
            "total_volume": round(total_volume, 2),
            "balance": round(summary["balance"], 2),
        })

    # Sort by total_score DESC, then transaction_count DESC, then volume DESC
    rankings.sort(
        key=lambda x: (x["total_score"], x["transaction_count"], x["total_volume"]),
        reverse=True
    )

    # Assign ranks (1-indexed)
    for i, entry in enumerate(rankings):
        entry["rank"] = i + 1

    return rankings
