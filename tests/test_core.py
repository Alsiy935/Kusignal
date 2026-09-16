import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"app"))
import numpy as np, pandas as pd
from core.features import add_features, align_mtf, make_labels, FEATURES

def sample(n=700, freq="5min", start="2025-01-01"):
    rng=np.random.default_rng(42); ret=rng.normal(0,.002,n)
    close=100*np.exp(np.cumsum(ret))
    high=close*(1+rng.uniform(0,.004,n)); low=close*(1-rng.uniform(0,.004,n))
    return pd.DataFrame({"time":pd.date_range(start,periods=n,freq=freq,tz="UTC"),
      "open":close,"close":close,"high":high,"low":low,
      "volume":rng.uniform(10,100,n),"turnover":1.0})

def test_features_and_labels():
    base=add_features(sample())
    freqs={"15min":"15min","1hour":"1h","4hour":"4h","1day":"1D"}
    starts={"15min":"2024-10-01","1hour":"2023-01-01","4hour":"2022-01-01","1day":"2010-01-01"}
    frames={tf:add_features(sample(25000,freqs[tf],starts[tf])) for tf in freqs}
    x=align_mtf(base,frames)
    x=make_labels(x,4,.003,-.003)
    clean=x.dropna(subset=FEATURES+["target"])
    assert len(clean)>300
    assert set(clean.target.astype(int).unique()) <= {0,1,2}

def test_label_determinism():
    x=add_features(sample(100))
    y=make_labels(x,4,.003,-.003)
    assert "target" in y
    assert pd.isna(y.target.iloc[-1])
