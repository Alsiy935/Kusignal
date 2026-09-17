import threading
import traceback
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView

from core.config import load
from core.exchange import KuCoin
from core.engine import LearningEngine


class UI(BoxLayout):
    def __init__(self, engine, **kw):
        super().__init__(orientation="vertical", padding=(18, 12, 18, 28), spacing=8, **kw)
        self.engine = engine
        self.info = Label(text="SelfLearningTrader Ultimate\nГотов.", font_size="17sp", halign="center", valign="middle", size_hint_y=None, height=80)
        self.info.bind(size=lambda obj, val: setattr(obj, "text_size", (obj.width, None)))
        self.add_widget(self.info)
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        box = BoxLayout(orientation="vertical", spacing=9, padding=(0, 4), size_hint_y=None)
        box.bind(minimum_height=box.setter("height"))
        for title, fn in [("СИНХРОНИЗИРОВАТЬ И ОБУЧИТЬ", self.train), ("LIVE-ПРОГНОЗ", self.predict), ("ЦИКЛ САМООБУЧЕНИЯ", self.learn), ("ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ", self.resolve)]:
            b = Button(text=title, size_hint_y=None, height=62)
            b.bind(on_release=fn); box.add_widget(b)
        scroll.add_widget(box); self.add_widget(scroll)

    def worker(self, fn):
        self.info.text = "Работаю...\nНе закрывайте приложение."
        def w():
            try: result = fn()
            except Exception:
                result = "Ошибка:\n" + traceback.format_exc()
            Clock.schedule_once(lambda dt: self.show(result), 0)
        threading.Thread(target=w, daemon=True).start()

    def show(self, value): self.info.text = str(value)
    def train(self, _):
        self.worker(lambda: (lambda r: f"Обучение завершено.\nAccuracy: {r['accuracy']:.3f}\nBalanced: {r['balanced_accuracy']:.3f}\nМодель принята: {r['accepted']}")(self.engine.train_from_fresh()))
    def predict(self, _):
        self.worker(lambda: (lambda r: f"ПРОГНОЗ: {r['prediction']}\nЦена: {r['price']:.8g}\nSHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}")(self.engine.predict_and_store()))
    def learn(self, _):
        self.worker(lambda: (lambda z: f"Цикл завершён.\nПроверено: {z[0]}\nAccuracy: {z[1]['accuracy']:.3f}")(self.engine.learning_cycle()))
    def resolve(self, _): self.worker(lambda: f"Новых прогнозов проверено: {self.engine.resolve_pending()}")


class TraderApp(App):
    def build(self):
        root = Path(self.user_data_dir)
        cfg = load(Path(__file__).resolve().parent / "config.json")
        return UI(LearningEngine(root, KuCoin(cfg["symbol"]), cfg))


if __name__ == "__main__": TraderApp().run()
