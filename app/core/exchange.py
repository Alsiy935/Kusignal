import time
import requests
import pandas as pd

BASE="https://api.kucoin.com"

class KuCoin:
    def __init__(self,symbol,timeout=25): self.symbol=symbol; self.timeout=timeout

    def _get(self,path,params):
        r=requests.get(BASE+path,params=params,timeout=self.timeout)
        r.raise_for_status()
        d=r.json()
        if d.get("code") not in (None,"200000"): raise RuntimeError(str(d))
        return d.get("data",d)

    def candles(self,tf,limit=1500):
        raw=self._get("/api/v1/market/candles",{"symbol":self.symbol,"type":tf,"limit":limit})
        x=pd.DataFrame(raw,columns=["time","open","close","high","low","volume","turnover"])
        for c in x.columns: x[c]=pd.to_numeric(x[c],errors="coerce")
        x["time"]=pd.to_datetime(x.time,unit="s",utc=True)
        return x.sort_values("time").drop_duplicates("time").reset_index(drop=True)

    def orderbook_imbalance(self):
        raw=self._get("/api/v1/market/orderbook/level2_20",{"symbol":self.symbol})
        bids=sum(float(q) for _,q in raw.get("bids",[]))
        asks=sum(float(q) for _,q in raw.get("asks",[]))
        return (bids-asks)/(bids+asks+1e-12)

    def current_market_metrics(self):
        # Spot public API may not expose futures metrics for every product.
        # Missing values remain NaN/0 and are never fabricated as historical facts.
        return {"book_imbalance":self.orderbook_imbalance(),
                "oi_change":0.0,"funding":0.0,"liquidation_bias":0.0}

    def snapshot(self,timeframes):
        frames={tf:self.candles(tf) for tf in timeframes}
        return frames
