"""
Middleware for rate limiting and request lifecycle.

Rate Limiter:
  - Sliding window algorithm per user_id
  - Configurable max requests per window
  - In-memory storage (resets on server restart — acceptable for this scope)
  - Returns 429 Too Many Requests when limit is exceeded
"""

import time
from collections import defaultdict
from typing import Optional


class RateLimiter:
    """
    Sliding window rate limiter.
    
    Tracks request timestamps per user_id and rejects requests
    that exceed the configured limit within the time window.
    
    Thread-safe via the GIL for single-process deployments.
    For multi-process, use Redis-based rate limiting instead.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Args:
            max_requests: Maximum allowed requests per window per user
            window_seconds: Duration of the sliding window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: str) -> tuple[bool, Optional[int]]:
        """
        Check if a request from user_id is allowed.
        
        Returns:
            (allowed: bool, retry_after_seconds: Optional[int])
            If not allowed, retry_after_seconds indicates when the
            client should retry.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Remove expired timestamps
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > cutoff
        ]

        if len(self._requests[user_id]) >= self.max_requests:
            # Calculate when the oldest request in the window expires
            oldest = self._requests[user_id][0]
            retry_after = int(oldest + self.window_seconds - now) + 1
            return False, retry_after

        # Record this request
        self._requests[user_id].append(now)
        return True, None

    def get_remaining(self, user_id: str) -> int:
        """Get the number of remaining requests allowed in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        active = [ts for ts in self._requests[user_id] if ts > cutoff]
        return max(0, self.max_requests - len(active))


# Global rate limiter instance
# 10 transactions per user per 60-second window
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
