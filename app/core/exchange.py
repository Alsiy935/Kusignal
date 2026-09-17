import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.kucoin.com"


class KuCoin:
    def __init__(self, symbol, timeout=25):
        self.symbol = symbol
        self.timeout = timeout

    def _get(self, path, params):
        url = BASE + path
        if params:
            url += "?" + urlencode(params)

        req = Request(
            url,
            headers={
                "User-Agent": "SelfLearningTrader/1.0",
                "Accept": "application/json",
            },
        )

        with urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))

        if data.get("code") not in (None, "200000"):
            raise RuntimeError(str(data))

        return data.get("data", data)

    def candles(self, tf, limit=300):
        raw = self._get(
            "/api/v1/market/candles",
            {
                "symbol": self.symbol,
                "type": tf,
                "limit": limit,
            },
        )

        rows = []

        for r in raw:
            if len(r) < 7:
                continue

            try:
                rows.append(
                    {
                        "time": int(float(r[0])),
                        "open": float(r[1]),
                        "close": float(r[2]),
                        "high": float(r[3]),
                        "low": float(r[4]),
                        "volume": float(r[5]),
                        "turnover": float(r[6]),
                    }
                )
            except (TypeError, ValueError):
                continue

        rows.sort(key=lambda x: x["time"])

        result = []
        seen = set()

        for row in rows:
            if row["time"] not in seen:
                seen.add(row["time"])
                result.append(row)

        return result

    def orderbook_imbalance(self):
        raw = self._get(
            "/api/v1/market/orderbook/level2_20",
            {"symbol": self.symbol},
        )

        bids = sum(float(q) for _, q in raw.get("bids", []))
        asks = sum(float(q) for _, q in raw.get("asks", []))

        return (bids - asks) / (bids + asks + 1e-12)

    def current_market_metrics(self):
        try:
            book = self.orderbook_imbalance()
        except Exception:
            book = 0.0

        return {
            "book_imbalance": float(book),
            "oi_change": 0.0,
            "funding": 0.0,
            "liquidation_bias": 0.0,
        }

    def snapshot(self, timeframes):
        return {
            tf: self.candles(tf)
            for tf in timeframes
        }
