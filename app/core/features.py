import numpy as np

BASE_FEATURES = [
    'ret1','ret3','ret8','rsi','ema12d','ema26d','macd','macds',
    'atrpct','bbpos','volz','rangepct','trend','volatility'
]
MTF_FEATURES = [
    'rsi_15','trend_15','volz_15', 'rsi_1h','trend_1h','volz_1h',
    'rsi_4h','trend_4h','volz_4h', 'rsi_1d','trend_1d','volz_1d'
]
MARKET_FEATURES = ['book_imbalance','oi_change','funding','liquidation_bias']
FEATURES = BASE_FEATURES + MTF_FEATURES + MARKET_FEATURES


def _arr(df, name):
    return np.asarray(df[name], dtype=float)


def _ema(a, span):
    a = np.asarray(a, dtype=float)
    out = np.empty_like(a); out[0] = a[0] if len(a) else 0.0
    alpha = 2.0 / (span + 1.0)
    for i in range(1, len(a)):
        out[i] = alpha * a[i] + (1-alpha) * out[i-1]
    return out


def _rolling_mean(a, n):
    out = np.full(len(a), np.nan)
    if len(a) >= n:
        cs = np.cumsum(np.r_[0.0, a])
        out[n-1:] = (cs[n:] - cs[:-n]) / n
    return out


def _rolling_std(a, n):
    out = np.full(len(a), np.nan)
    if len(a) >= n:
        for i in range(n-1, len(a)):
            out[i] = np.std(a[i-n+1:i+1], ddof=1)
    return out


def _rolling_mean_std(a, n):
    return _rolling_mean(a,n), _rolling_std(a,n)


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.maximum(d, 0.0); dn = np.maximum(-d, 0.0)
    au = _ema_alpha(up, 1.0/n); ad = _ema_alpha(dn, 1.0/n)
    return 100.0 - 100.0/(1.0 + au/(ad + 1e-12))


def _ema_alpha(a, alpha):
    a=np.asarray(a,float); out=np.empty_like(a)
    if not len(a): return out
    out[0]=a[0]
    for i in range(1,len(a)): out[i]=alpha*a[i]+(1-alpha)*out[i-1]
    return out


def add_features(df):
    t=np.asarray(df['time']); c=_arr(df,'close'); h=_arr(df,'high'); l=_arr(df,'low'); v=_arr(df,'volume')
    n=len(c); x={'time':t.copy(),'close':c.copy(),'open':_arr(df,'open'),'high':h.copy(),'low':l.copy(),'volume':v.copy()}
    ret1=np.full(n,np.nan); ret3=np.full(n,np.nan); ret8=np.full(n,np.nan)
    if n>1: ret1[1:]=c[1:]/c[:-1]-1
    if n>3: ret3[3:]=c[3:]/c[:-3]-1
    if n>8: ret8[8:]=c[8:]/c[:-8]-1
    e12=_ema(c,12); e26=_ema(c,26); mac=e12-e26
    pc=np.r_[c[0],c[:-1]]; tr=np.maximum.reduce([h-l,np.abs(h-pc),np.abs(l-pc)])
    atr=_ema_alpha(tr,1/14)
    mid,sd=_rolling_mean_std(c,20); vm,vs=_rolling_mean_std(v,30)
    x.update({
      'ret1':ret1,'ret3':ret3,'ret8':ret8,'rsi':_rsi(c),'ema12d':c/(e12+1e-12)-1,
      'ema26d':c/(e26+1e-12)-1,'macd':mac/(c+1e-12),'macds':_ema(mac,9)/(c+1e-12),
      'atrpct':atr/(c+1e-12),'bbpos':(c-(mid-2*sd))/(4*sd+1e-12),
      'volz':(v-vm)/(vs+1e-12),'rangepct':(h-l)/(c+1e-12),'trend':(e12-e26)/(c+1e-12),
      'volatility':_rolling_std(ret1,30)
    })
    return x


def _nearest_values(target_t, source_t, source):
    tt=np.asarray(target_t); st=np.asarray(source_t); out={}
    if len(st)==0:
        return None
    order=np.argsort(st); st=st[order]
    idx=np.searchsorted(st,tt,side='right')-1; idx=np.clip(idx,0,len(st)-1)
    for k,a in source.items():
        if k=='time': continue
        aa=np.asarray(a)
        if len(aa)!=len(source_t): raise ValueError(f'MTF feature {k} length {len(aa)} != time length {len(source_t)}')
        out[k]=aa[order][idx]
    return out


def align_mtf(base, frames):
    x={k:np.asarray(v).copy() for k,v in base.items()}
    target=x['time']; n=len(target)
    suffixes={'15min':'15','1hour':'1h','4hour':'4h','1day':'1d'}
    for tf,suf in suffixes.items():
        if tf not in frames or len(frames[tf]['time'])==0:
            for k in ('rsi','trend','volz'): x[f'{k}_{suf}']=np.full(n,np.nan)
            continue
        z=add_features(frames[tf]); vals=_nearest_values(target,z['time'],z)
        for k in ('rsi','trend','volz'): x[f'{k}_{suf}']=vals[k]
    for c in MARKET_FEATURES:
        if c not in x: x[c]=np.zeros(n,dtype=float)
    return x


def make_labels(x,horizon,long_threshold,short_threshold):
    c=np.asarray(x['close'],float); n=len(c); fut=np.full(n,np.nan); h=int(horizon)
    if h>0 and n>h: fut[:-h]=c[h:]/c[:-h]-1
    y=np.full(n,np.nan)
    y[fut>=long_threshold]=2; y[fut<=short_threshold]=0
    mid=(fut<long_threshold)&(fut>short_threshold); y[mid]=1
    z={k:np.asarray(v).copy() for k,v in x.items()}; z['target']=y
    return z
