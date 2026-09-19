import json, os, ssl, time, urllib.parse, urllib.request, http.client, threading
import certifi

# Android often has no usable OpenSSL CA path for Python. Use the bundled Mozilla CA set.
_CA_BUNDLE = certifi.where()
os.environ.setdefault("SSL_CERT_FILE", _CA_BUNDLE)
os.environ.setdefault("REQUESTS_CA_BUNDLE", _CA_BUNDLE)
import numpy as np

BASE='https://api.kucoin.com'
FUTURES_BASE='https://api-futures.kucoin.com'
TF_SECONDS={'5min':300,'15min':900,'1hour':3600,'4hour':14400,'1day':86400}
TF_API={'5min':'5min','15min':'15min','1hour':'1hour','4hour':'4hour','1day':'1day'}

class KuCoin:
    def __init__(self,symbol='XBTUSDTM',timeout=25):
        self.timeout=timeout
        self.ctx=ssl.create_default_context(cafile=_CA_BUNDLE)
        self.ctx.check_hostname=True
        self.ctx.verify_mode=ssl.CERT_REQUIRED
        self._contract_cache={}
        self._connections={}
        self._conn_lock=threading.Lock()
        self._last_request=0.0
        self._request_gap=0.10
        self.set_symbol(symbol)

    def set_symbol(self,symbol):
        s=str(symbol).strip().upper()
        if not s:
            s='XBTUSDTM'
        # KuCoin Futures uses XBTUSDTM as the BTC perpetual contract symbol.
        # The UI/config uses the human-readable BTC-USDT name, so normalize
        # both directions here. Without this mapping BTC-USDT became
        # BTCUSDTM, which is not a valid KuCoin Futures contract and caused
        # empty 5m candle responses.
        if s in ('BTC-USDT','BTCUSDT','BTCUSDTM'):
            self.futures_symbol='XBTUSDTM'
        elif s.endswith('USDTM'):
            self.futures_symbol=s
        else:
            self.futures_symbol=s.replace('-USDT','USDTM')
        self.symbol=self.display_symbol(self.futures_symbol)

    @staticmethod
    def display_symbol(contract):
        s=str(contract).upper()
        if s.endswith('USDTM'):
            base=s[:-5]
            if base=='XBT': base='BTC'
            return base+'-USDT'
        return s

    def _request_json(self, base, path, params):
        q=urllib.parse.urlencode(params or {})
        target=path + (('?' + q) if q else '')
        parsed=urllib.parse.urlsplit(base)
        host=parsed.netloc
        headers={'User-Agent':'SelfLearningTrader/2.2','Accept':'application/json','Connection':'keep-alive'}
        last=None
        for attempt in range(5):
            try:
                with self._conn_lock:
                    wait=self._request_gap-(time.monotonic()-self._last_request)
                    if wait>0: time.sleep(wait)
                    conn=self._connections.get(host)
                    if conn is None:
                        conn=http.client.HTTPSConnection(host,timeout=self.timeout,context=self.ctx)
                        self._connections[host]=conn
                    self._last_request=time.monotonic()
                conn.request('GET',target,headers=headers)
                resp=conn.getresponse()
                raw=resp.read()
                status=resp.status
                if status==429 or status>=500:
                    raise RuntimeError(f'HTTP {status}')
                if status>=400:
                    raise RuntimeError(f'HTTP {status}: {raw[:300].decode("utf-8",errors="replace")}')
                d=json.loads(raw.decode('utf-8'))
                if d.get('code') not in (None,'200000'):
                    raise RuntimeError(str(d))
                return d.get('data',d)
            except Exception as e:
                last=e
                with self._conn_lock:
                    c=self._connections.pop(host,None)
                    try:
                        if c: c.close()
                    except Exception: pass
                if attempt>=4: break
                time.sleep((0.35,0.8,1.6,3.0)[attempt])
        raise last if last else RuntimeError('KuCoin request failed')

    def _get(self,path,params):
        return self._request_json(BASE,path,params)

    def active_symbols(self):
        # Use the documented public Futures endpoint. The old /api/ua/*
        # instrument endpoint is not the canonical Futures contract list and
        # can return an incomplete/incompatible set on some accounts/regions.
        data=self._get_futures('/api/v1/contracts/active',{})
        rows=data.get('data',data) if isinstance(data,dict) else data
        out=[]
        for x in rows or []:
            s=str(x.get('symbol','')).upper()
            settle=str(x.get('settleCurrency','')).upper()
            expire=x.get('expireDate')
            # Scanner target: live USDT-margined perpetual contracts.
            if not s.endswith('USDTM') or settle not in ('','USDT'):
                continue
            if expire not in (None, '', 0, '0'):
                continue
            out.append({'contract':s,'display':self.display_symbol(s),
                        'base':x.get('baseCurrency',''),
                        'volume':float(x.get('volumeOf24h',x.get('volume',0)) or 0),
                        'turnover':float(x.get('turnoverOf24h',x.get('turnover',0)) or 0)})
        # Stable deterministic order; BTC first, then liquidity.
        out.sort(key=lambda x:(x['contract']!='XBTUSDTM',-x['turnover'],x['display']))
        if not out:
            raise RuntimeError('KuCoin Futures: список активных USDT-перпетуалов пуст')
        return out

    def all_tickers(self):
        data=self._get_futures('/api/v1/allTickers',{})
        rows=data.get('data',data) if isinstance(data,dict) else data
        return rows or []

    def candles(self,tf,limit=5000):
        limit=max(1,int(limit)); sec=TF_SECONDS[tf]; end=int(time.time()); chunks=[]; cursor=end
        # Official Futures kline endpoint accepts granularity + from/to.
        # Paginate backwards so there is no artificial 500-row history cap.
        while len(chunks)<limit:
            start=max(0,cursor-sec*199)
            data=self._get_futures('/api/v1/kline/query',{
                'symbol':self.futures_symbol,'granularity':int(sec/60),
                'from':start*1000,'to':cursor*1000
            })
            rows=data.get('data',data) if isinstance(data,dict) else data
            if not rows: break
            rows=list(rows); chunks.extend(rows)
            times=[int(r[0]) for r in rows]
            oldest=min(times)
            if oldest>=cursor*1000: break
            cursor=max(0,oldest//1000-sec)
            if len(rows)<2: break
        rows={int(r[0]):r for r in chunks}; rows=sorted(rows.values(),key=lambda r:int(r[0]))[-limit:]
        if not rows: raise RuntimeError(f'KuCoin не вернул свечи {tf} для {self.futures_symbol}')
        a=np.asarray(rows,dtype=object)
        # KuCoin Futures REST format is [time, open, high, low, close, volume, turnover].
        # The previous build incorrectly treated the HIGH field as CLOSE, which could
        # distort RSI/MACD/ATR and produce absurd 100% predictions.
        return {'time':a[:,0].astype(np.int64)*1000,'open':a[:,1].astype(float),
                'high':a[:,2].astype(float),'low':a[:,3].astype(float),
                'close':a[:,4].astype(float),'volume':a[:,5].astype(float),
                'turnover':a[:,6].astype(float) if a.shape[1]>6 else np.zeros(len(a))}

    def orderbook_imbalance(self):
        try:
            data=self._get('/api/ua/v1/market/orderbook',{'tradeType':'FUTURES','symbol':self.futures_symbol,'depth':'20'})
            bids=data.get('bids',[]) if isinstance(data,dict) else []
            asks=data.get('asks',[]) if isinstance(data,dict) else []
            b=sum(float(x[1]) for x in bids); a=sum(float(x[1]) for x in asks)
            return (b-a)/(b+a+1e-12)
        except Exception: return 0.0

    def contract_info(self):
        """Return contract-specific risk/fee parameters from KuCoin, cached per symbol."""
        if self.futures_symbol in self._contract_cache:
            return self._contract_cache[self.futures_symbol]
        try:
            data=self._get_futures('/api/v1/contracts/'+urllib.parse.quote(self.futures_symbol,safe=''),{})
            out=data if isinstance(data,dict) else {}
            self._contract_cache[self.futures_symbol]=out
            return out
        except Exception:
            return {}

    def _get_futures(self,path,params):
        return self._request_json(FUTURES_BASE,path,params)

    def current_market_metrics(self):
        return {'book_imbalance':self.orderbook_imbalance(),'oi_change':0.0,'funding':0.0,'liquidation_bias':0.0}
