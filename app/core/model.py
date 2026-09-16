from pathlib import Path
import json, time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from .features import FEATURES

NAMES={0:"SHORT",1:"WAIT",2:"LONG"}

class ModelManager:
    def __init__(self,root:Path):
        self.root=root; self.models=root/"models"; self.models.mkdir(parents=True,exist_ok=True)
        self.champion=self.models/"champion.joblib"
        self.meta=self.models/"champion.json"

    def _new(self):
        return HistGradientBoostingClassifier(max_iter=300,learning_rate=.04,
            max_leaf_nodes=15,l2_regularization=1.5,random_state=42)

    def train(self,x):
        if len(x)<500: raise ValueError(f"Need at least 500 rows; got {len(x)}")
        cut=int(len(x)*.8); tr=x.iloc[:cut]; te=x.iloc[cut:]
        m=self._new(); m.fit(tr[FEATURES],tr.target.astype(int))
        pred=m.predict(te[FEATURES])
        acc=float(accuracy_score(te.target,pred))
        bal=float(balanced_accuracy_score(te.target,pred))
        stamp=time.strftime("%Y%m%d_%H%M%S")
        candidate=self.models/f"model_{stamp}.joblib"
        joblib.dump({"model":m,"features":FEATURES,"rows":len(tr),"created":stamp},candidate)
        old_acc=-1
        if self.meta.exists():
            old_acc=float(json.loads(self.meta.read_text()).get("accuracy",-1))
        accepted=acc>=old_acc
        if accepted:
            joblib.dump({"model":m,"features":FEATURES,"rows":len(tr),"created":stamp},self.champion)
            self.meta.write_text(json.dumps({"accuracy":acc,"balanced_accuracy":bal,
                "rows":len(tr),"created":stamp},indent=2),encoding="utf-8")
        return {"accuracy":acc,"balanced_accuracy":bal,"rows":len(x),"accepted":accepted}

    def predict(self,row):
        if not self.champion.exists(): raise FileNotFoundError("No trained model.")
        obj=joblib.load(self.champion); m=obj["model"]
        p=m.predict_proba(row[FEATURES])[0]
        probs={int(c):float(v) for c,v in zip(m.classes_,p)}
        cls=int(m.predict(row[FEATURES])[0])
        return NAMES[cls],probs
