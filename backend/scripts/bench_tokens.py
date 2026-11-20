"""Load test: 1,000,000 signed-token verifications through the real resolver path.

Measures the CPU cost of what every QR scan does before touching MongoDB:
base32 parse → batch lookup (in-process cache) → HMAC-SHA256 verify →
range check.  Run:  cd backend && python scripts/bench_tokens.py [N]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tokens  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
KEY = os.urandom(32)
BATCHES = {bid: {"bid": bid, "serial_start": 0, "count": 10_000_000} for bid in range(1, 51)}

toks = [tokens.encode_token(KEY, 1 + (i % 50), i) for i in range(10_000)]
t = time.perf_counter()
ok = 0
for i in range(N):
    tok = toks[i % len(toks)]
    p = tokens.parse_token(tok)
    if not p:
        continue
    bid, serial, body, sig = p
    b = BATCHES.get(bid)
    if b and tokens.verify_sig(KEY, body, sig) and b["serial_start"] <= serial < b["serial_start"] + b["count"]:
        ok += 1
dt = time.perf_counter() - t
print(f"{N:,} verifications: {dt:.2f}s  ({N / dt:,.0f}/s, {dt / N * 1e6:.1f} µs each), valid={ok:,}")
assert ok == N
# Tampered tokens must all fail
bad = 0
for tok in toks[:10_000]:
    forged = tok[:-3] + ("AAA" if tok[-3:] != "AAA" else "BBB")
    p = tokens.parse_token(forged)
    bad += bool(p and tokens.verify_sig(KEY, p[2], p[3]))
print(f"forged tokens accepted: {bad} / 10,000")
assert bad == 0
