from pathlib import Path
import json
import time
import numpy as np
from .features import FEATURES

NAMES = {0: "SHORT", 1: "WAIT", 2: "LONG"}


class NumpyClassifier:
    def __init__(self, n_features, n_classes=3):
        self.n_features = n_features; self.n_classes = n_classes
        self.weights = np.zeros((n_features, n_classes), dtype=np.float64)
        self.bias = np.zeros(n_classes, dtype=np.float64)
        self.means = np.zeros(n_features, dtype=np.float64)
        self.stds = np.ones(n_features, dtype=np.float64)

    def fit(self, X, y, epochs=220, learning_rate=0.025, l2=0.0005):
        X = np.asarray(X, dtype=float); y = np.asarray(y, dtype=int)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        self.means = np.mean(X, axis=0); self.stds = np.std(X, axis=0); self.stds[self.stds < 1e-8] = 1.0
        X = (X - self.means) / self.stds
        Y = np.zeros((len(y), self.n_classes)); Y[np.arange(len(y)), y] = 1.0
        n = float(max(1, len(X)))
        for _ in range(epochs):
            z = X @ self.weights + self.bias; z -= np.max(z, axis=1, keepdims=True)
            p = np.exp(np.clip(z, -50, 50)); p /= np.sum(p, axis=1, keepdims=True)
            e = p - Y
            self.weights -= learning_rate * ((X.T @ e) / n + l2 * self.weights)
            self.bias -= learning_rate * np.mean(e, axis=0)
        return self

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float); X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        X = (X - self.means) / self.stds
        z = X @ self.weights + self.bias; z -= np.max(z, axis=1, keepdims=True)
        p = np.exp(np.clip(z, -50, 50)); return p / np.sum(p, axis=1, keepdims=True)

    def predict(self, X): return np.argmax(self.predict_proba(X), axis=1)


class ModelManager:
    def __init__(self, root: Path):
        self.models = Path(root) / "models"; self.models.mkdir(parents=True, exist_ok=True)
        self.champion = self.models / "champion.npz"; self.meta = self.models / "champion.json"

    def _new(self): return NumpyClassifier(len(FEATURES), 3)

    def _load(self):
        if not self.champion.exists():
            return None
        try:
            z = np.load(self.champion)
            m = self._new()
            weights = np.asarray(z["weights"], dtype=float)
            bias = np.asarray(z["bias"], dtype=float)
            means = np.asarray(z["means"], dtype=float)
            stds = np.asarray(z["stds"], dtype=float)
            # Do not use a model produced by an older app version with a
            # different feature vector. That used to cause errors such as
            # "operands could not be broadcast together with shapes (33,) (100,)".
            expected = (len(FEATURES), 3)
            if weights.shape != expected or bias.shape != (3,) or means.shape != (len(FEATURES),) or stds.shape != (len(FEATURES),):
                return None
            if not (np.all(np.isfinite(weights)) and np.all(np.isfinite(bias)) and
                    np.all(np.isfinite(means)) and np.all(np.isfinite(stds))):
                return None
            stds = np.where(np.abs(stds) < 1e-8, 1.0, stds)
            m.weights = weights; m.bias = bias; m.means = means; m.stds = stds
            return m
        except Exception:
            return None

    def train(self, x):
        n = len(x["target"])
        if n < 500: raise ValueError(f"Not enough training rows: {n}. Minimum is 500.")
        X = np.column_stack([x[f] for f in FEATURES]); y = np.asarray(x["target"], dtype=int)
        cut = max(1, int(n * 0.8)); trX, teX = X[:cut], X[cut:]; try_y, te_y = y[:cut], y[cut:]
        m = self._new().fit(trX, try_y)
        pred = m.predict(teX) if len(teX) else np.array([], dtype=int)
        accuracy = float(np.mean(pred == te_y)) if len(te_y) else 0.0
        scores = [float(np.mean(pred[te_y == c] == c)) for c in range(3) if np.any(te_y == c)]
        balanced = float(np.mean(scores)) if scores else 0.0
        stamp = time.strftime("%Y%m%d_%H%M%S")
        np.savez(self.models / f"model_{stamp}.npz", weights=m.weights, bias=m.bias, means=m.means, stds=m.stds)
        old = -1.0
        try: old = float(json.loads(self.meta.read_text()).get("accuracy", -1.0))
        except Exception: pass
        accepted = accuracy >= old
        if accepted:
            np.savez(self.champion, weights=m.weights, bias=m.bias, means=m.means, stds=m.stds)
            self.meta.write_text(json.dumps({
                "engine":"numpy_softmax_v3",
                "accuracy":accuracy,
                "balanced_accuracy":balanced,
                "rows":n,
                "created":stamp,
                "feature_count":len(FEATURES),
                "features":FEATURES,
            }, indent=2))
        return {"accuracy": accuracy, "balanced_accuracy": balanced, "rows": n, "accepted": accepted}

    def predict(self, row):
        m = self._load()
        if m is None:
            raise FileNotFoundError("Нет совместимой обученной модели. Сначала нажмите «СИНХРОНИЗИРОВАТЬ И ОБУЧИТЬ».")
        try:
            X = np.column_stack([np.asarray(row[f], dtype=float).reshape(-1) for f in FEATURES])
        except KeyError as e:
            raise ValueError(f"Отсутствует признак модели: {e.args[0]}") from e
        if X.shape[1] != len(FEATURES):
            raise ValueError(f"Неверное число признаков: {X.shape[1]}, требуется {len(FEATURES)}")
        p = m.predict_proba(X)[0]; cls = int(np.argmax(p))
        return NAMES[cls], {i: float(p[i]) for i in range(3)}
