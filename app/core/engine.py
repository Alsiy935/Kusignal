from pathlib import Path
import json
import time
import numpy as np
from .features import add_features, align_mtf, make_labels, FEATURES
from .model import ModelManager


class LearningEngine:
    def __init__(self, root, exchange, config):
        self.root = Path(root); self.exchange = exchange; self.cfg = config
        self.data = self.root / "data"; self.data.mkdir(exist_ok=True)
        self.logs = self.root / "logs"; self.logs.mkdir(exist_ok=True)
        self.mm = ModelManager(self.root)
        self.pending = self.logs / "pending.json"

    def collect(self):
        return {tf: self.exchange.candles(tf, min(self.cfg.get("history_limit", 1500), 1000)) for tf in self.cfg["timeframes"]}

    def build_training(self, frames):
        base = add_features(frames["5min"])
        x = align_mtf(base, {k:v for k,v in frames.items() if k != "5min"})
        x = make_labels(x, self.cfg["horizon_bars"], self.cfg["long_threshold"], self.cfg["short_threshold"])
        base_len = len(x["time"])
        if base_len == 0:
            raise ValueError("Нет базовых 5min свечей для обучения")

        # Hard guarantee: every training column must have exactly the same
        # number of rows as the 5min base frame.  Older builds could leave
        # one MTF/market column at its source length (for example 33) while
        # the base frame had another length (for example 100), which then
        # crashed inside the in-place boolean mask operation.
        for f in FEATURES:
            arr = np.asarray(x.get(f, []), dtype=float).reshape(-1)
            if arr.size != base_len:
                raise ValueError(
                    f"Несовпадение длины признака {f}: {arr.size} вместо {base_len}. "
                    "Данные этого таймфрейма не выровнены."
                )
            x[f] = arr

        target = np.asarray(x.get("target", []), dtype=float).reshape(-1)
        if target.size != base_len:
            raise ValueError(
                f"Несовпадение длины target: {target.size} вместо {base_len}"
            )
        x["target"] = target

        # Market features are constant over the current training snapshot.
        # Fill them only after the length check above, so they can never
        # introduce a second row count.
        for k in ["book_imbalance","oi_change","funding","liquidation_bias"]:
            x[k] = np.zeros(base_len, dtype=float)

        good = np.ones(base_len, dtype=bool)
        for f in FEATURES + ["target"]:
            good &= np.isfinite(x[f])
        return {k: np.asarray(v)[good] if np.asarray(v).ndim == 1 and np.asarray(v).size == base_len else v for k,v in x.items()}

    def train_from_fresh(self):
        return self.mm.train(self.build_training(self.collect()))

    def live_row(self):
        frames = self.collect()
        base = add_features(frames["5min"])
        x = align_mtf(base, {k: v for k, v in frames.items() if k != "5min"})
        metrics = self.exchange.current_market_metrics()
        base_len = len(x["time"])
        for k, v in metrics.items():
            x[k] = np.full(base_len, float(v), dtype=float)

        # Every live feature must have exactly the same row count as the
        # base timeframe before selecting the latest row.  This prevents a
        # short MTF history from ever producing an out-of-bounds index.
        for f in FEATURES:
            if f not in x:
                raise ValueError(f"Отсутствует признак: {f}")
            arr = np.asarray(x[f]).reshape(-1)
            if arr.size != base_len:
                raise ValueError(
                    f"Некорректная длина признака {f}: {arr.size}, "
                    f"ожидалось {base_len}"
                )
        if base_len == 0:
            raise ValueError("KuCoin не вернул свечи 5min")
        i = base_len - 1
        return {k: np.asarray([x[k][i]], dtype=float) if k != "time" else np.asarray([x[k][i]], dtype=np.int64) for k in x}

    def predict_and_store(self):
        row = self.live_row(); pred, probs = self.mm.predict(row)
        price = float(row["close"][0]); ts = int(row["time"][0])
        result = {"prediction":pred,"price":price,"p_short":probs[0],"p_wait":probs[1],"p_long":probs[2],"time":ts}
        self._save_pending(result, row); return result

    def _save_pending(self, result, row):
        data = []
        if self.pending.exists():
            try: data = json.loads(self.pending.read_text())
            except Exception: data = []
        item = {"id": str(int(time.time()*1000)), **result, "resolved": 0}
        item["features"] = {f: float(row[f][0]) for f in FEATURES}
        data.append(item); data = data[-500:]
        self.pending.write_text(json.dumps(data))

    def resolve_pending(self):
        if not self.pending.exists(): return 0
        try: data = json.loads(self.pending.read_text())
        except Exception: return 0
        if not data: return 0
        bars = self.exchange.candles("5min", min(self.cfg.get("history_limit",1500),500))
        times = np.asarray([r["time"] for r in bars]); closes = np.asarray([r["close"] for r in bars])
        changed = 0
        for item in data:
            if item.get("resolved"): continue
            idx = np.searchsorted(times, int(item["time"]), side="right")
            h = int(self.cfg["horizon_bars"])
            if idx + h > len(closes): continue
            ret = closes[idx+h-1] / float(item["price"]) - 1.0
            item["actual"] = "LONG" if ret >= self.cfg["long_threshold"] else ("SHORT" if ret <= self.cfg["short_threshold"] else "WAIT")
            item["return"] = float(ret); item["resolved"] = 1; changed += 1
        self.pending.write_text(json.dumps(data))
        return changed

    def learning_cycle(self):
        resolved = self.resolve_pending(); trained = self.train_from_fresh(); return resolved, trained
