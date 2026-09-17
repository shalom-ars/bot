import time
from collections import deque
from typing import Dict, List, Optional


class LatencyTracker:
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._samples: Dict[str, deque] = {
            "market_discovery_ms": deque(maxlen=window_size),
            "chainlink_ms": deque(maxlen=window_size),
            "clob_ms": deque(maxlen=window_size),
            "strategy_ms": deque(maxlen=window_size),
            "risk_ms": deque(maxlen=window_size),
            "execution_ms": deque(maxlen=window_size),
            "db_write_ms": deque(maxlen=window_size),
            "api_response_ms": deque(maxlen=window_size),
        }
        self.stale_threshold_ms = 5000.0

    def record(self, metric: str, duration_ms: float):
        if metric not in self._samples:
            self._samples[metric] = deque(maxlen=self.window_size)
        self._samples[metric].append(duration_ms)

    def get_percentiles(self, metric: str) -> Dict[str, float]:
        samples = list(self._samples.get(metric, []))
        if not samples:
            return {"count": 0, "latest": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        
        def pct(p):
            idx = int(p * n)
            return sorted_samples[min(idx, n - 1)]

        return {
            "count": n,
            "latest": round(samples[-1], 2),
            "p50": round(pct(0.50), 2),
            "p95": round(pct(0.95), 2),
            "p99": round(pct(0.99), 2),
        }

    def get_summary(self) -> Dict[str, dict]:
        return {metric: self.get_percentiles(metric) for metric in self._samples}

    def is_degraded(self) -> bool:
        for metric in ["chainlink_ms", "clob_ms"]:
            p = self.get_percentiles(metric)
            if p["count"] >= 5 and p["p95"] > self.stale_threshold_ms:
                return True
        return False


latency_tracker = LatencyTracker()
