"""
Rate limiting (tiêu chí 7) — sliding window 60 giây trên Redis sorted set.

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request / 60 giây
  • Vượt → HTTP 429 + header Retry-After
  • State nằm trong Redis → mọi worker/instance dùng chung, còn nguyên khi restart agent
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def _bucket(key: str) -> str:
    # Không lưu API key thô trong Redis
    return "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:16]


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    bucket = _bucket(key)
    now = time.time()
    try:
        pipe = r.pipeline()  # MULTI/EXEC: 4 lệnh chạy nguyên tử
        pipe.zremrangebyscore(bucket, 0, now - WINDOW_SECONDS)
        pipe.zcard(bucket)
        pipe.zadd(bucket, {f"{now}-{uuid.uuid4().hex[:8]}": now})
        pipe.expire(bucket, WINDOW_SECONDS + 1)
        _, count, _, _ = pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")

    if count >= limit:
        # Request bị từ chối không được tính vào cửa sổ
        r.zremrangebyscore(bucket, now, now)
        oldest = r.zrange(bucket, 0, 0, withscores=True)
        retry_after = int(oldest[0][1] + WINDOW_SECONDS - now) + 1 if oldest else WINDOW_SECONDS
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} requests per minute",
            headers={"Retry-After": str(max(retry_after, 1))},
        )
