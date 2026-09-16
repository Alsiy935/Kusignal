import numpy as np
import pandas as pd

BASE_FEATURES=[
"ret1","ret3","ret8","rsi","ema12d","ema26d","macd","macds",
"atrpct","bbpos","volz","rangepct","trend","volatility"
]
MTF_FEATURES=[
"rsi_15","trend_15","volz_15",
"rsi_1h","trend_1h","volz_1h",
"rsi_4h","trend_4h","volz_4h",
"rsi_1d","trend_1d","volz_1d"
]
MARKET_FEATURES=["book_imbalance","oi_change","funding","liquidation_bias"]
FEATURES=BASE_FEATURES+MTF_FEATURES+MARKET_FEATURES

def rsi(s,n=14):
    d=s.diff()
    up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+up/(dn+1e-12))

def add_features(df):
    x=df.copy()
    c=x.close.astype(float)
    x["ret1"]=c.pct_change()
    x["ret3"]=c.pct_change(3)
    x["ret8"]=c.pct_change(8)
    x["rsi"]=rsi(c)
    e12=c.ewm(span=12,adjust=False).mean()
    e26=c.ewm(span=26,adjust=False).mean()
    x["ema12d"]=c/e12-1
    x["ema26d"]=c/e26-1
    m=e12-e26
    x["macd"]=m/c
    x["macds"]=m.ewm(span=9,adjust=False).mean()/c
    pc=c.shift(1)
    tr=pd.concat([(x.high-x.low),(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1)
    x["atrpct"]=tr.ewm(alpha=1/14,adjust=False).mean()/c
    mid=c.rolling(20).mean(); sd=c.rolling(20).std()
    x["bbpos"]=(c-(mid-2*sd))/(4*sd+1e-12)
    vm=x.volume.rolling(30)
    x["volz"]=(x.volume-vm.mean())/(vm.std()+1e-12)
    x["rangepct"]=(x.high-x.low)/(c+1e-12)
    x["trend"]=(e12-e26)/(c+1e-12)
    x["volatility"]=x.ret1.rolling(30).std()
    return x

def align_mtf(base, frames):
    x=base.sort_values("time").copy()
    for key,y in frames.items():
        z=add_features(y)[["time","rsi","trend","volz"]].copy()
        suffix={"15min":"15","1hour":"1h","4hour":"4h","1day":"1d"}[key]
        z=z.rename(columns={"rsi":f"rsi_{suffix}","trend":f"trend_{suffix}","volz":f"volz_{suffix}"})
        x=pd.merge_asof(x,z.sort_values("time"),on="time",direction="backward")
    for c in MARKET_FEATURES:
        if c not in x: x[c]=0.0
    return x

def make_labels(x,horizon,long_threshold,short_threshold):
    fut=x.close.shift(-horizon)/x.close-1
    x=x.copy()
    x["target"]=np.select([fut>=long_threshold,fut<=short_threshold],[2,0],default=1)
    x.loc[fut.isna(),"target"]=np.nan
    return x
