from pathlib import Path
import pandas as pd, numpy as np, time
from .features import add_features, align_mtf, make_labels, FEATURES
from .model import ModelManager

class LearningEngine:
    def __init__(self,root,exchange,config):
        self.root=Path(root); self.exchange=exchange; self.cfg=config
        self.data=self.root/"data"; self.data.mkdir(exist_ok=True)
        self.logs=self.root/"logs"; self.logs.mkdir(exist_ok=True)
        self.mm=ModelManager(self.root)
        self.pending=self.logs/"pending.csv"
        self.predictions=self.logs/"predictions.csv"

    def collect(self):
        frames={tf:self.exchange.candles(tf,self.cfg["history_limit"]) for tf in self.cfg["timeframes"]}
        for tf,x in frames.items():
            x.to_csv(self.data/f"{self.exchange.symbol}_{tf}.csv",index=False)
        return frames

    def build_training(self,frames):
        base=add_features(frames["5min"])
        others={k:v for k,v in frames.items() if k!="5min"}
        x=align_mtf(base,others)
        x=make_labels(x,self.cfg["horizon_bars"],self.cfg["long_threshold"],self.cfg["short_threshold"])
        # No fabricated historical L2/futures data.
        x["book_imbalance"]=0.0; x["oi_change"]=0.0
        x["funding"]=0.0; x["liquidation_bias"]=0.0
        return x.dropna(subset=FEATURES+["target"]).copy()

    def _combine_experience(self,historical):
        if self.data.joinpath("experience.csv").exists():
            old=pd.read_csv(self.data/"experience.csv",parse_dates=["time"])
            cols=[c for c in old.columns if c in historical.columns]
            if set(FEATURES+["target"]).issubset(old.columns):
                historical=pd.concat([historical,old[historical.columns]],ignore_index=True)
        historical=historical.drop_duplicates("time",keep="last").sort_values("time")
        historical.to_csv(self.data/"experience.csv",index=False)
        return historical

    def train_from_fresh(self):
        frames=self.collect()
        x=self._combine_experience(self.build_training(frames))
        result=self.mm.train(x)
        return result

    def live_row(self):
        frames=self.collect()
        base=add_features(frames["5min"])
        x=align_mtf(base,{k:v for k,v in frames.items() if k!="5min"})
        metrics=self.exchange.current_market_metrics()
        for k,v in metrics.items(): x[k]=float(v)
        return x.dropna(subset=FEATURES).iloc[[-1]].copy()

    def predict_and_store(self):
        row=self.live_row()
        pred,probs=self.mm.predict(row)
        now=str(row.time.iloc[0])
        result={"id":f"{int(time.time()*1000)}","time":now,"price":float(row.close.iloc[0]),
                "prediction":pred,"p_short":probs.get(0,0),"p_wait":probs.get(1,0),
                "p_long":probs.get(2,0),"resolved":0}
        # Store the exact feature snapshot so this prediction can become training experience later.
        pending_row={"id":result["id"],"time":now,"price":result["price"],"prediction":pred,"resolved":0}
        for f in FEATURES: pending_row[f]=float(row[f].iloc[0])
        pd.DataFrame([pending_row]).to_csv(self.pending,mode="a",header=not self.pending.exists(),index=False)
        pd.DataFrame([result]).to_csv(self.predictions,mode="a",header=not self.predictions.exists(),index=False)
        return result

    def resolve_pending(self):
        if not self.pending.exists(): return 0
        p=pd.read_csv(self.pending)
        if p.empty:return 0
        bars=self.exchange.candles("5min",self.cfg["history_limit"])
        closes=bars[["time","close"]].sort_values("time")
        closes.time=pd.to_datetime(closes.time,utc=True)
        changed=0; new=[]
        h=self.cfg["horizon_bars"]
        for i,r in p[p.resolved.fillna(0)==0].iterrows():
            t=pd.Timestamp(r.time)
            if t.tzinfo is None:t=t.tz_localize("UTC")
            later=closes[closes.time>t].head(h)
            if len(later)<h: continue
            final=float(later.close.iloc[-1]); ret=final/float(r.price)-1
            actual="LONG" if ret>=self.cfg["long_threshold"] else ("SHORT" if ret<=self.cfg["short_threshold"] else "WAIT")
            target={"LONG":2,"WAIT":1,"SHORT":0}[actual]
            exp={f:float(r[f]) for f in FEATURES}
            exp.update({"time":str(t),"target":target})
            new.append(exp)
            p.loc[i,"resolved"]=1;p.loc[i,"actual"]=actual;p.loc[i,"return"]=ret
            changed+=1
        p.to_csv(self.pending,index=False)
        if new:
            ep=self.data/"experience.csv"
            df=pd.DataFrame(new)
            if ep.exists():
                old=pd.read_csv(ep)
                df=pd.concat([old,df],ignore_index=True).drop_duplicates("time",keep="last")
            df.to_csv(ep,index=False)
        return changed

    def learning_cycle(self):
        resolved=self.resolve_pending()
        trained=self.train_from_fresh()
        return resolved,trained
