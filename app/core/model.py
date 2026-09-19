from pathlib import Path
import json, time
import numpy as np
from .features import FEATURES

NAMES={0:'SHORT',1:'WAIT',2:'LONG'}

class NumpyClassifier:
    def __init__(self,n_features,n_classes=3):
        self.n_features=n_features; self.n_classes=n_classes
        self.weights=np.zeros((n_features,n_classes)); self.bias=np.zeros(n_classes)
        self.means=np.zeros(n_features); self.stds=np.ones(n_features)
    def fit(self,X,y,epochs=260,learning_rate=.025,l2=.0005):
        X=np.asarray(X,float); y=np.asarray(y,int); X=np.nan_to_num(X,nan=0,posinf=0,neginf=0)
        self.means=np.mean(X,axis=0); self.stds=np.std(X,axis=0); self.stds[self.stds<1e-8]=1
        Z=(X-self.means)/self.stds; Y=np.zeros((len(y),3)); Y[np.arange(len(y)),y]=1; n=max(1,len(Z))
        for _ in range(epochs):
            s=Z@self.weights+self.bias; s-=np.max(s,axis=1,keepdims=True); p=np.exp(np.clip(s,-50,50)); p/=np.sum(p,axis=1,keepdims=True)
            e=p-Y; self.weights-=learning_rate*((Z.T@e)/n+l2*self.weights); self.bias-=learning_rate*np.mean(e,axis=0)
        return self
    def predict_proba(self,X):
        X=np.nan_to_num(np.asarray(X,float),nan=0,posinf=0,neginf=0); Z=(X-self.means)/self.stds
        s=Z@self.weights+self.bias; s-=np.max(s,axis=1,keepdims=True); p=np.exp(np.clip(s,-50,50)); return p/np.sum(p,axis=1,keepdims=True)
    def predict(self,X): return np.argmax(self.predict_proba(X),axis=1)

class ModelManager:
    def __init__(self,root,symbol='XBTUSDTM'):
        safe=''.join(ch if ch.isalnum() else '_' for ch in str(symbol))
        self.models=Path(root)/'models_v7_self_learning'/safe; self.models.mkdir(parents=True,exist_ok=True)
        self.champion=self.models/'champion.npz'; self.meta=self.models/'champion.json'
    def _new(self): return NumpyClassifier(len(FEATURES),3)
    def _save(self,path,m): np.savez(path,weights=m.weights,bias=m.bias,means=m.means,stds=m.stds)
    def _load_path(self,path):
        if not Path(path).exists(): return None
        try:
            z=np.load(path); m=self._new()
            if z['weights'].shape!=(len(FEATURES),3): return None
            m.weights=z['weights'];m.bias=z['bias'];m.means=z['means'];m.stds=np.where(np.abs(z['stds'])<1e-8,1,z['stds'])
            return m
        except Exception:return None
    def _scores(self,y,p):
        acc=float(np.mean(p==y)) if len(y) else 0.0
        per=[]
        for c in range(3):
            mask=y==c
            per.append(float(np.mean(p[mask]==c)) if np.any(mask) else 0.0)
        bal=float(np.mean(per))
        return acc,bal,per
    def train(self,x,min_rows=500,test_fraction=.2):
        n=len(x['target'])
        if n<min_rows: raise ValueError(f'Not enough training rows: {n}. Minimum is {min_rows}.')
        X=np.column_stack([x[f] for f in FEATURES]); y=np.asarray(x['target'],int)
        cut=max(1,min(n-1,int(n*(1-test_fraction))))
        trX,teX=X[:cut],X[cut:]; trY,teY=y[:cut],y[cut:]
        # Walk-forward holdout: only earlier rows train the candidate, later rows test it.
        m=self._new().fit(trX,trY); pred=m.predict(teX); acc,bal,per=self._scores(teY,pred)
        stamp=time.strftime('%Y%m%d_%H%M%S'); candidate=self.models/f'model_{stamp}.npz'; self._save(candidate,m)
        oldbal=-1; oldacc=-1
        if self.meta.exists():
            try:
                meta=json.loads(self.meta.read_text()); oldbal=float(meta.get('balanced_accuracy',-1)); oldacc=float(meta.get('accuracy',-1))
            except Exception: pass
        accepted=(bal>oldbal+1e-9) or (abs(bal-oldbal)<=1e-9 and acc>=oldacc)
        if accepted:
            self._save(self.champion,m)
            self.meta.write_text(json.dumps({'engine':'numpy_softmax_v7_self_learning','accuracy':acc,'balanced_accuracy':bal,'class_accuracy':per,'rows':n,'train_rows':cut,'test_rows':len(teY),'created':stamp,'feature_count':len(FEATURES),'features':FEATURES},indent=2))
        return {'accuracy':acc,'balanced_accuracy':bal,'class_accuracy':per,'rows':n,'train_rows':cut,'test_rows':len(teY),'accepted':accepted}
    def has_champion(self):
        return self.champion.exists() and self._load_path(self.champion) is not None

    def predict(self,row):
        m=self._load_path(self.champion)
        if m is None: raise FileNotFoundError('Нет совместимой обученной модели. Сначала выполните обучение.')
        X=np.column_stack([np.asarray(row[f],float).reshape(-1) for f in FEATURES]); p=m.predict_proba(X)[0]; cls=int(np.argmax(p))
        return NAMES[cls],{i:float(p[i]) for i in range(3)}
