from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class VehicleRateLimiter:
    def __init__(self, limit: int = 15, window_seconds: float = 10.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, vehicle_id: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events[vehicle_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


vehicle_rate_limiter = VehicleRateLimiter()
