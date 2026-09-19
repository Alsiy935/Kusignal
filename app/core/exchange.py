import json, ssl, time, urllib.parse, urllib.request
import numpy as np

BASE='https://api.kucoin.com'
TF_SECONDS={'5min':300,'15min':900,'1hour':3600,'4hour':14400,'1day':86400}
TF_API={'5min':'5min','15min':'15min','1hour':'1hour','4hour':'4hour','1day':'1day'}

class KuCoin:
    def __init__(self,symbol='XBTUSDTM',timeout=25):
        self.timeout=timeout
        self.ctx=ssl.create_default_context()
        self.set_symbol(symbol)

    def set_symbol(self,symbol):
        s=str(symbol).strip().upper()
        if not s:
            s='XBTUSDTM'
        self.futures_symbol=s if s.endswith('M') else s.replace('-USDT','USDTM')
        self.symbol=self.display_symbol(self.futures_symbol)

    @staticmethod
    def display_symbol(contract):
        s=str(contract).upper()
        if s.endswith('USDTM'):
            base=s[:-5]
            if base=='XBT': base='BTC'
            return base+'-USDT'
        return s

    def _get(self,path,params):
        q=urllib.parse.urlencode(params); req=urllib.request.Request(BASE+path+'?'+q,headers={'User-Agent':'SelfLearningTrader/2.0'})
        with urllib.request.urlopen(req,timeout=self.timeout,context=self.ctx) as r:
            d=json.loads(r.read().decode('utf-8'))
        if d.get('code') not in (None,'200000'):
            raise RuntimeError(str(d))
        return d.get('data',d)

    def active_symbols(self):
        data=self._get('/api/ua/v2/market/instrument',{'tradeType':'FUTURES'})
        rows=data.get('list',data) if isinstance(data,dict) else data
        out=[]
        for x in rows or []:
            s=str(x.get('symbol','')).upper()
            status=str(x.get('status',x.get('state',''))).lower()
            if s.endswith('USDTM') and status not in ('offline','delisted','deactivate','disabled'):
                out.append({'contract':s,'display':self.display_symbol(s),'base':x.get('baseCurrency','')})
        # Keep stable order, BTC first.
        out.sort(key=lambda x:(x['contract']!='XBTUSDTM',x['display']))
        return out

    def all_tickers(self):
        data=self._get('/api/ua/v1/market/ticker',{'tradeType':'FUTURES'})
        rows=data.get('ticker',data) if isinstance(data,dict) else data
        return rows or []

    def candles(self,tf,limit=5000):
        limit=max(1,int(limit)); sec=TF_SECONDS[tf]; end=int(time.time()); chunks=[]; cursor=end
        while len(chunks)<limit:
            start=max(0,cursor-sec*199)
            data=self._get('/api/ua/v2/market/kline',{
                'symbol':self.futures_symbol,'tradeType':'FUTURES','klineType':'TRADE',
                'interval':TF_API[tf],'startAt':start,'endAt':cursor
            })
            rows=data.get('list',data) if isinstance(data,dict) else data
            if not rows: break
            rows=list(rows); chunks.extend(rows)
            times=[int(r[0]) for r in rows]; oldest=min(times)
            if oldest>=cursor: break
            cursor=oldest-sec
            if len(rows)<2: break
        rows={int(r[0]):r for r in chunks}; rows=sorted(rows.values(),key=lambda r:int(r[0]))[-limit:]
        if not rows: raise RuntimeError(f'KuCoin не вернул свечи {tf} для {self.futures_symbol}')
        a=np.asarray(rows,dtype=object)
        return {'time':a[:,0].astype(np.int64)*1000,'open':a[:,1].astype(float),'close':a[:,2].astype(float),
                'high':a[:,3].astype(float),'low':a[:,4].astype(float),'volume':a[:,5].astype(float),
                'turnover':a[:,6].astype(float) if a.shape[1]>6 else np.zeros(len(a))}

    def orderbook_imbalance(self):
        try:
            data=self._get('/api/ua/v1/market/orderbook',{'tradeType':'FUTURES','symbol':self.futures_symbol,'depth':'20'})
            bids=data.get('bids',[]) if isinstance(data,dict) else []
            asks=data.get('asks',[]) if isinstance(data,dict) else []
            b=sum(float(x[1]) for x in bids); a=sum(float(x[1]) for x in asks)
            return (b-a)/(b+a+1e-12)
        except Exception: return 0.0

    def current_market_metrics(self):
        return {'book_imbalance':self.orderbook_imbalance(),'oi_change':0.0,'funding':0.0,'liquidation_bias':0.0}
