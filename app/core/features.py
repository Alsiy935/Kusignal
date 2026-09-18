import numpy as np

BASE_FEATURES = [
    "ret1", "ret3", "ret8", "rsi", "ema12d", "ema26d", "macd", "macds",
    "atrpct", "bbpos", "volz", "rangepct", "trend", "volatility"
]
MTF_FEATURES = [
    "rsi_15", "trend_15", "volz_15", "rsi_1h", "trend_1h", "volz_1h",
    "rsi_4h", "trend_4h", "volz_4h", "rsi_1d", "trend_1d", "volz_1d"
]
MARKET_FEATURES = ["book_imbalance", "oi_change", "funding", "liquidation_bias"]
FEATURES = BASE_FEATURES + MTF_FEATURES + MARKET_FEATURES


def _ema(x, span):
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def _rolling_mean(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    cs = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _rolling_std(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    for i in range(n - 1, len(x)):
        out[i] = np.std(x[i - n + 1:i + 1])
    return out


def _pct_change(x, n=1):
    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = x[n:] / x[:-n] - 1.0
    return out


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.maximum(d, 0.0)
    dn = np.maximum(-d, 0.0)
    au = _ema(up, 2 * n - 1)
    ad = _ema(dn, 2 * n - 1)
    return 100.0 - 100.0 / (1.0 + au / (ad + 1e-12))


def add_features(rows):
    c = np.asarray([r["close"] for r in rows], dtype=float)
    h = np.asarray([r["high"] for r in rows], dtype=float)
    l = np.asarray([r["low"] for r in rows], dtype=float)
    v = np.asarray([r["volume"] for r in rows], dtype=float)
    e12 = _ema(c, 12); e26 = _ema(c, 26); macd = e12 - e26
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = _ema(tr, 27)
    mid = _rolling_mean(c, 20); sd = _rolling_std(c, 20)
    vm = _rolling_mean(v, 30); vs = _rolling_std(v, 30)
    ret1 = _pct_change(c, 1)
    out = {
        "time": np.asarray([r["time"] for r in rows], dtype=np.int64),
        "close": c,
        "ret1": ret1, "ret3": _pct_change(c, 3), "ret8": _pct_change(c, 8),
        "rsi": _rsi(c), "ema12d": c / (e12 + 1e-12) - 1,
        "ema26d": c / (e26 + 1e-12) - 1, "macd": macd / (c + 1e-12),
        "macds": _ema(macd, 9) / (c + 1e-12), "atrpct": atr / (c + 1e-12),
        "bbpos": (c - (mid - 2 * sd)) / (4 * sd + 1e-12),
        "volz": (v - vm) / (vs + 1e-12), "rangepct": (h - l) / (c + 1e-12),
        "trend": (e12 - e26) / (c + 1e-12), "volatility": _rolling_std(ret1, 30),
    }
    return out


def _nearest_values(target_times, source, names):
    """Align lower-frequency features to target timestamps safely.

    Never index a source feature array with an index that belongs to a
    different-sized array.  KuCoin may return different history lengths for
    each timeframe, and source timestamps are explicitly sorted first.
    """
    target_times = np.asarray(target_times, dtype=np.int64).reshape(-1)
    st = np.asarray(source.get("time", []), dtype=np.int64).reshape(-1)
    if target_times.size == 0:
        return {name: np.empty(0, dtype=float) for name in names}
    if st.size == 0:
        return {name: np.full(target_times.size, np.nan, dtype=float) for name in names}

    order = np.argsort(st, kind="stable")
    st = st[order]
    idx = np.searchsorted(st, target_times, side="right") - 1
    valid = idx >= 0
    idx = np.clip(idx, 0, st.size - 1)

    result = {}
    for name in names:
        src = np.asarray(source.get(name, []), dtype=float).reshape(-1)
        if src.size != order.size:
            raise ValueError(
                f"Некорректная длина признака {name}: {src.size}, "
                f"ожидалось {order.size}"
            )
        src = src[order]
        a = np.full(target_times.size, np.nan, dtype=float)
        a[valid] = src[idx[valid]]
        result[name] = a
    return result

def align_mtf(base, frames):
    x = {k: np.array(v, copy=True) for k, v in base.items()}
    mapping = {"15min": "15", "1hour": "1h", "4hour": "4h", "1day": "1d"}
    # Every configured MTF feature is always created with exactly the same
    # length as the 5min base frame, even if KuCoin returns a short/empty
    # history for one timeframe.
    for key, suf in mapping.items():
        y = frames.get(key)
        if y:
            z = add_features(y)
            vals = _nearest_values(x["time"], z, ["rsi", "trend", "volz"])
        else:
            vals = {name: np.full(len(x["time"]), np.nan, dtype=float)
                    for name in ("rsi", "trend", "volz")}
        x[f"rsi_{suf}"] = vals["rsi"]
        x[f"trend_{suf}"] = vals["trend"]
        x[f"volz_{suf}"] = vals["volz"]
    for c in MARKET_FEATURES:
        if c not in x:
            x[c] = np.zeros(len(x["time"]), dtype=float)
    return x


def make_labels(x, horizon, long_threshold, short_threshold):
    out = {k: np.array(v, copy=True) for k, v in x.items()}
    c = out["close"]
    target = np.full(len(c), np.nan)
    if len(c) > horizon:
        ret = c[horizon:] / c[:-horizon] - 1.0
        target[:-horizon] = np.where(ret >= long_threshold, 2, np.where(ret <= short_threshold, 0, 1))
    out["target"] = target
    return out
