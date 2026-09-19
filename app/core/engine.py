from pathlib import Path
import json, time
import numpy as np
from .features import add_features, align_mtf, make_labels, FEATURES
from .model import ModelManager

class LearningEngine:
    def __init__(self,root,exchange,config):
        self.root=Path(root); self.exchange=exchange; self.cfg=config
        self.data=self.root/'data'; self.data.mkdir(exist_ok=True); self.logs=self.root/'logs'; self.logs.mkdir(exist_ok=True)
        self.mm=ModelManager(self.root, self.exchange.futures_symbol); self.pending=self.logs/f'{self.exchange.futures_symbol}_pending.json'; self.predictions=self.logs/f'{self.exchange.futures_symbol}_predictions.json'; self.experience=self.data/f'{self.exchange.futures_symbol}_experience.npz'
    def set_symbol(self, symbol):
        self.exchange.set_symbol(symbol)
        self.mm=ModelManager(self.root, self.exchange.futures_symbol)
        self.pending=self.logs/f'{self.exchange.futures_symbol}_pending.json'
        self.predictions=self.logs/f'{self.exchange.futures_symbol}_predictions.json'
        self.experience=self.data/f'{self.exchange.futures_symbol}_experience.npz'

    def collect(self):
        return {tf:self.exchange.candles(tf,int(self.cfg.get('history_limit',5000))) for tf in self.cfg['timeframes']}
    def build_training(self,frames):
        base=add_features(frames['5min']); x=align_mtf(base,{k:v for k,v in frames.items() if k!='5min'})
        x=make_labels(x,int(self.cfg['horizon_bars']),float(self.cfg['long_threshold']),float(self.cfg['short_threshold']))
        n=len(x['time'])
        for f in FEATURES:
            if f not in x: x[f]=np.zeros(n)
            a=np.asarray(x[f],float).reshape(-1)
            if len(a)!=n: raise ValueError(f'Несовпадение длины признака {f}: {len(a)} вместо {n}')
            x[f]=a
        y=np.asarray(x['target'],float); good=np.isfinite(y)
        for f in FEATURES: good &= np.isfinite(x[f])
        return {f:np.asarray(x[f])[good] for f in FEATURES}|{'target':y[good],'time':np.asarray(x['time'])[good]}
    def _load_exp(self):
        if not self.experience.exists(): return None
        try:
            z=np.load(self.experience); return {k:z[k] for k in z.files}
        except Exception:return None
    def _save_exp(self,x): np.savez(self.experience,**x)
    def _merge_experience(self,hist):
        old=self._load_exp()
        if not old:return hist
        # Experience is already resolved against future market data; append only unique timestamps.
        all_t=np.concatenate([np.asarray(hist['time']),np.asarray(old['time'])]); order=np.argsort(all_t); _,idx=np.unique(all_t[order],return_index=True); keep=order[idx]
        out={'time':all_t[keep]}
        for f in FEATURES+['target']:
            out[f]=np.concatenate([hist[f],old[f]])[keep]
        return out
    def train_from_fresh(self):
        frames=self.collect(); hist=self.build_training(frames); data=self._merge_experience(hist); return self.mm.train(data,int(self.cfg.get('min_training_rows',500)),float(self.cfg.get('test_fraction',.2)))
    def live_row(self):
        frames=self.collect(); base=add_features(frames['5min']); x=align_mtf(base,{k:v for k,v in frames.items() if k!='5min'}); n=len(x['time'])
        metrics=self.exchange.current_market_metrics()
        for k,v in metrics.items(): x[k]=np.full(n,float(v))
        for f in FEATURES:
            a=np.asarray(x.get(f,[])).reshape(-1)
            if len(a)!=n: raise ValueError(f'Некорректная длина признака {f}: {len(a)}, ожидалось {n}')
        if n==0: raise ValueError('KuCoin не вернул 5min свечи')
        i=n-1; return {k:np.asarray([v[i]]) for k,v in x.items()}
    def _signal_levels(self,row,pred):
        price=float(row['close'][0]); atr=float(row['atrpct'][0])*price; atr=max(atr,price*0.001)
        if pred=='LONG': return price,price-1.2*atr,price+1.8*atr,price+2.7*atr,price+3.6*atr
        if pred=='SHORT': return price,price+1.2*atr,price-1.8*atr,price-2.7*atr,price-3.6*atr
        return price,price-1.0*atr,price,price,price
    def predict_and_store(self):
        row=self.live_row(); pred,probs=self.mm.predict(row); entry,sl,tp1,tp2,tp3=self._signal_levels(row,pred); ts=int(row['time'][0]); item={'id':str(int(time.time()*1000)),'symbol':self.exchange.symbol,'exchange_symbol':self.exchange.futures_symbol,'contract':self.exchange.futures_symbol,'time':ts,'price':float(row['close'][0]),'prediction':pred,'p_short':probs[0],'p_wait':probs[1],'p_long':probs[2],'entry':entry,'sl':sl,'tp1':tp1,'tp2':tp2,'tp3':tp3,'horizon_bars':int(self.cfg['horizon_bars']),'resolved':0}
        item['features']={f:float(row[f][0]) for f in FEATURES}; self._append_json(self.predictions,item); self._append_json(self.pending,item); return item
    def _read_json(self,path):
        try:return json.loads(path.read_text()) if path.exists() else []
        except Exception:return []
    def _write_json(self,path,data): path.write_text(json.dumps(data,ensure_ascii=False))
    def _append_json(self,path,item): data=self._read_json(path); data.append(item); self._write_json(path,data[-1000:])
    def resolve_pending(self):
        data=self._read_json(self.pending); unresolved=[x for x in data if not x.get('resolved')]
        if not unresolved:return 0
        bars=self.exchange.candles('5min',min(int(self.cfg.get('history_limit',5000)),5000)); t=np.asarray(bars['time']); h=np.asarray(bars['high']); l=np.asarray(bars['low']); c=np.asarray(bars['close']); changed=0; resolved_items=[]
        for item in unresolved:
            idx=int(np.searchsorted(t,int(item['time']),side='right')); horizon=int(item['horizon_bars'])
            if idx+horizon>len(c): continue
            entry=float(item['entry']); direction=item['prediction']; sl=float(item['sl']); tp1=float(item['tp1']); window=slice(idx,idx+horizon)
            outcome='WAIT'; ret=float(c[idx+horizon-1]/entry-1); hit='TIME'
            if direction=='LONG':
                for j in range(idx,idx+horizon):
                    if l[j]<=sl: outcome='SHORT'; hit='SL'; break
                    if h[j]>=tp1: outcome='LONG'; hit='TP1'; break
                if hit=='TIME': outcome='LONG' if ret>=self.cfg['long_threshold'] else ('SHORT' if ret<=self.cfg['short_threshold'] else 'WAIT')
            elif direction=='SHORT':
                for j in range(idx,idx+horizon):
                    if h[j]>=sl: outcome='LONG'; hit='SL'; break
                    if l[j]<=tp1: outcome='SHORT'; hit='TP1'; break
                if hit=='TIME': outcome='LONG' if ret>=self.cfg['long_threshold'] else ('SHORT' if ret<=self.cfg['short_threshold'] else 'WAIT')
            item.update({'resolved':1,'actual':outcome,'return':ret,'hit':hit,'resolved_at':int(t[idx+horizon-1])}); changed+=1; resolved_items.append(item)
        if changed:
            # Replace resolved entries while keeping unresolved ones.
            self._write_json(self.pending,[x for x in data if not x.get('resolved')]+resolved_items)
            self._append_experience(resolved_items)
            # Also append resolved state to prediction history.
            preds=self._read_json(self.predictions); byid={x['id']:x for x in resolved_items}
            for p in preds:
                if p.get('id') in byid:p.update(byid[p['id']])
            self._write_json(self.predictions,preds[-1000:])
        return changed
    def _append_experience(self,items):
        old=self._load_exp(); rows=[x for x in items if x.get('actual') in ('LONG','SHORT','WAIT')]
        if not rows:return
        new={'time':np.asarray([x['time'] for x in rows]),'target':np.asarray([{'SHORT':0,'WAIT':1,'LONG':2}[x['actual']] for x in rows],int)}
        for f in FEATURES:new[f]=np.asarray([x['features'][f] for x in rows],float)
        if old:
            ts=np.concatenate([old['time'],new['time']]); order=np.argsort(ts); keep=order[np.unique(ts[order],return_index=True)[1]]
            merged={'time':ts[keep]}
            for f in FEATURES+['target']: merged[f]=np.concatenate([old[f],new[f]])[keep]
            self._save_exp(merged)
        else:self._save_exp(new)
    def stats(self):
        p=self._read_json(self.predictions); resolved=[x for x in p if x.get('resolved')]; correct=[x for x in resolved if x.get('actual')==x.get('prediction')]
        return {'predictions':len(p),'pending':len([x for x in p if not x.get('resolved')]),'resolved':len(resolved),'correct':len(correct),'live_accuracy':(len(correct)/len(resolved) if resolved else None)}
    def learning_cycle(self):
        resolved=self.resolve_pending(); trained=self.train_from_fresh(); return resolved,trained,self.stats()

    def scan_all(self, progress=None):
        symbols=self.exchange.active_symbols(); results=[]
        original=self.exchange.futures_symbol
        for i,item in enumerate(symbols):
            try:
                self.set_symbol(item['contract'])
                if not self.mm.has_champion():
                    train=self.train_from_fresh()
                else:
                    train=None
                resolved=self.resolve_pending()
                r=self.predict_and_store()
                r['contract']=item['contract']
                r['trained_now']=bool(train)
                r['resolved_now']=resolved
                results.append(r)
            except Exception as e:
                results.append({'symbol':item['display'],'contract':item['contract'],'error':str(e)})
            if progress: progress(i+1,len(symbols),item['display'])
        self.set_symbol(original)
        return results
