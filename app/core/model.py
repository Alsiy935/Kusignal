from pathlib import Path
import json
import time

import joblib
import numpy as np
import pandas as pd

from .features import FEATURES


NAMES = {
    0: "SHORT",
    1: "WAIT",
    2: "LONG",
}


class NumpyClassifier:
    def __init__(self, n_features, n_classes=3):
        self.n_features = n_features
        self.n_classes = n_classes
        self.weights = np.zeros((n_features, n_classes), dtype=np.float64)
        self.bias = np.zeros(n_classes, dtype=np.float64)
        self.means = np.zeros(n_features, dtype=np.float64)
        self.stds = np.ones(n_features, dtype=np.float64)
        self.classes_ = np.arange(n_classes)

    def _softmax(self, z):
        z = z - np.max(z, axis=1, keepdims=True)
        e = np.exp(np.clip(z, -50, 50))
        return e / np.sum(e, axis=1, keepdims=True)

    def fit(
        self,
        X,
        y,
        epochs=400,
        learning_rate=0.03,
        l2=0.0005,
    ):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.int64)

        X = np.nan_to_num(
            X,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

        self.means = np.mean(X, axis=0)
        self.stds = np.std(X, axis=0)
        self.stds[self.stds < 1e-8] = 1.0

        Xn = (X - self.means) / self.stds

        Y = np.zeros((len(y), self.n_classes), dtype=np.float64)
        Y[np.arange(len(y)), y] = 1.0

        n = float(max(len(Xn), 1))

        for _ in range(epochs):
            logits = Xn @ self.weights + self.bias
            probs = self._softmax(logits)

            error = probs - Y

            grad_w = (Xn.T @ error) / n
            grad_b = np.mean(error, axis=0)

            grad_w += l2 * self.weights

            self.weights -= learning_rate * grad_w
            self.bias -= learning_rate * grad_b

        self.classes_ = np.arange(self.n_classes)
        return self

    def _prepare(self, X):
        X = np.asarray(X, dtype=np.float64)

        X = np.nan_to_num(
            X,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

        return (X - self.means) / self.stds

    def predict_proba(self, X):
        Xn = self._prepare(X)
        logits = Xn @ self.weights + self.bias
        return self._softmax(logits)

    def predict(self, X):
        return np.argmax(self.predict_proba(X), axis=1)


class ModelManager:
    def __init__(self, root: Path):
        self.root = root
        self.models = root / "models"

        self.models.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.champion = self.models / "champion.joblib"
        self.meta = self.models / "champion.json"

    def _new(self):
        return NumpyClassifier(
            n_features=len(FEATURES),
            n_classes=3,
        )

    def _load(self):
        if not self.champion.exists():
            return None

        try:
            obj = joblib.load(self.champion)

            if not isinstance(obj, dict):
                return None

            if obj.get("engine") != "numpy_softmax_v1":
                return None

            model = obj.get("model")

            if model is None:
                return None

            return model

        except Exception:
            return None

    def train(self, x):
        required = list(FEATURES) + ["target"]

        missing = [
            c for c in required
            if c not in x.columns
        ]

        if missing:
            raise ValueError(
                "Missing columns: "
                + ", ".join(missing)
            )

        if len(x) < 500:
            raise ValueError(
                f"Not enough training rows: {len(x)}. "
                "Minimum is 500."
            )

        cut = int(len(x) * 0.8)

        tr = x.iloc[:cut].copy()
        te = x.iloc[cut:].copy()

        model = self._new()

        model.fit(
            tr[FEATURES].to_numpy(),
            tr["target"].astype(int).to_numpy(),
        )

        pred = model.predict(
            te[FEATURES].to_numpy()
        )

        actual = te["target"].astype(int).to_numpy()

        accuracy = float(
            np.mean(pred == actual)
        )

        balanced_scores = []

        for cls in range(3):
            mask = actual == cls

            if np.any(mask):
                balanced_scores.append(
                    float(
                        np.mean(
                            pred[mask] == actual[mask]
                        )
                    )
                )

        balanced_accuracy = (
            float(np.mean(balanced_scores))
            if balanced_scores
            else 0.0
        )

        stamp = time.strftime(
            "%Y%m%d_%H%M%S"
        )

        candidate = (
            self.models
            / f"model_{stamp}.joblib"
        )

        package = {
            "engine": "numpy_softmax_v1",
            "model": model,
            "features": FEATURES,
            "rows": len(tr),
            "created": stamp,
        }

        joblib.dump(
            package,
            candidate,
        )

        old_accuracy = -1.0

        if self.meta.exists():
            try:
                old_accuracy = float(
                    json.loads(
                        self.meta.read_text(
                            encoding="utf-8"
                        )
                    ).get(
                        "accuracy",
                        -1,
                    )
                )
            except Exception:
                old_accuracy = -1.0

        accepted = accuracy >= old_accuracy

        if accepted:
            joblib.dump(
                package,
                self.champion,
            )

            self.meta.write_text(
                json.dumps(
                    {
                        "engine": "numpy_softmax_v1",
                        "accuracy": accuracy,
                        "balanced_accuracy": balanced_accuracy,
                        "rows": len(x),
                        "created": stamp,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        return {
            "accuracy": accuracy,
            "balanced_accuracy": balanced_accuracy,
            "rows": len(x),
            "accepted": accepted,
        }

    def predict(self, row):
        model = self._load()

        if model is None:
            raise FileNotFoundError(
                "No compatible trained model."
            )

        if not isinstance(row, pd.DataFrame):
            raise TypeError(
                "row must be a pandas DataFrame"
            )

        missing = [
            c for c in FEATURES
            if c not in row.columns
        ]

        if missing:
            raise ValueError(
                "Missing feature columns: "
                + ", ".join(missing)
            )

        values = row[FEATURES].to_numpy()

        probabilities = model.predict_proba(
            values
        )[0]

        probabilities = np.asarray(
            probabilities,
            dtype=np.float64,
        )

        probabilities = np.clip(
            probabilities,
            0.0,
            1.0,
        )

        total = float(
            np.sum(probabilities)
        )

        if total > 0:
            probabilities /= total

        probs = {
            int(cls): float(
                probabilities[cls]
            )
            for cls in range(3)
        }

        cls = int(
            np.argmax(probabilities)
        )

        return NAMES[cls], probs
