import time

import tokens

KEY = b"k" * 32


def test_token_roundtrip_and_format():
    tok = tokens.encode_token(KEY, 1234, 98765)
    assert len(tok) == tokens.TOKEN_LEN and tok.isupper()
    bid, serial, body, sig = tokens.parse_token(tok)
    assert (bid, serial) == (1234, 98765)
    assert tokens.verify_sig(KEY, body, sig)
    # lower-case input (typed / some scanners) still parses
    assert tokens.parse_token(tok.lower())[:2] == (1234, 98765)


def test_tampered_or_foreign_tokens_fail():
    tok = tokens.encode_token(KEY, 7, 1)
    bid, serial, body, sig = tokens.parse_token(tok)
    assert not tokens.verify_sig(b"other-key-" * 4, body, sig)
    # flip one character of the signature part
    bad = tok[:-1] + ("A" if tok[-1] != "A" else "B")
    parsed = tokens.parse_token(bad)
    assert parsed is None or not tokens.verify_sig(KEY, parsed[2], parsed[3])
    # change the serial but keep the old signature
    forged = tokens._body(7, 2) + sig
    import base64

    ftok = base64.b32encode(forged).decode().rstrip("=")
    p = tokens.parse_token(ftok)
    assert not tokens.verify_sig(KEY, p[2], p[3])
    assert tokens.parse_token("not-a-token") is None
    assert tokens.parse_token("A" * 27) is None


def test_short_code_check_and_parsing():
    code = tokens.short_code(KEY, "PK24", 137)
    assert code.startswith("PK24-0137-") and len(code.split("-")[2]) == 4
    ev, serial, check = tokens.parse_code(code.lower().replace("-", " "))
    assert (ev, serial) == ("PK24", 137)
    assert tokens.verify_code(KEY, ev, serial, check)
    assert not tokens.verify_code(KEY, ev, 138, check)
    assert tokens.parse_code("PK240137ABCD") is None  # separators required


def test_qr_url_uses_alphanumeric_friendly_form():
    assert tokens.qr_url("https://info-tag.in", "ABC") == "HTTPS://INFO-TAG.IN/T/ABC"
    assert tokens.qr_url("https://x.in/app", "ABC") == "https://x.in/app/t/ABC"


def test_env_key_parsing():
    keys = tokens.parse_env_keys("k1:" + "a" * 40 + ", k2:" + "b" * 40)
    assert list(keys) == ["k1", "k2"] and all(len(v) == 32 for v in keys.values())
    try:
        tokens.parse_env_keys("k1:short")
        raise AssertionError("short secret accepted")
    except ValueError:
        pass


def test_verification_throughput_100k():
    """100k verifications must take well under a second per 10k on any box.

    (The 1M-verification load test lives in scripts/bench_tokens.py.)
    """
    toks = [tokens.encode_token(KEY, 1, i) for i in range(1000)]
    t = time.perf_counter()
    ok = 0
    for _ in range(100):
        for tok in toks:
            _, _, body, sig = tokens.parse_token(tok)
            ok += tokens.verify_sig(KEY, body, sig)
    assert ok == 100_000
    assert time.perf_counter() - t < 10
