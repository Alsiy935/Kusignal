import json
from pathlib import Path

DEFAULT = {
    "symbol":"BTC-USDT","timeframes":["5min","15min","1hour","4hour","1day"],
    "history_limit":1500,"horizon_bars":4,"long_threshold":0.003,
    "short_threshold":-0.003,"retrain_every":25,"min_training_rows":500,
    "test_fraction":0.2,"champion_min_accuracy":0.0,"refresh_seconds":60
}

def load(path: Path):
    if not path.exists():
        path.write_text(json.dumps(DEFAULT,ensure_ascii=False,indent=2),encoding="utf-8")
    data=json.loads(path.read_text(encoding="utf-8"))
    out=DEFAULT.copy(); out.update(data); return out
