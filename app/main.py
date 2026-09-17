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
        super().__init__(orientation="vertical", padding=(12, 8, 12, 10), spacing=6, **kw)
        self.engine = engine
        self.menu_open = False

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=58, spacing=6)
        self.title = Label(text="SelfLearningTrader Ultimate", font_size="18sp", halign="left", valign="middle")
        self.title.bind(size=lambda obj, val: setattr(obj, "text_size", val))
        header.add_widget(self.title)
        self.menu_button = Button(text="...", font_size="22sp", size_hint=(None, 1), width=58, background_normal="")
        self.menu_button.bind(on_release=self.toggle_menu)
        header.add_widget(self.menu_button)
        self.add_widget(header)

        self.scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width="5dp", scroll_type=["bars", "content"])
        self.content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6, padding=(0, 0, 0, 12))
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.add_widget(self.scroll)

        self.info = Label(text="Готов.", font_size="17sp", halign="center", valign="top", size_hint_y=None, padding=(4, 8))
        self.info.bind(width=lambda obj, val: setattr(obj, "text_size", (max(0, val - 8), None)))
        self.info.bind(texture_size=lambda obj, val: setattr(obj, "height", max(80, val[1] + 16)))
        self.content.add_widget(self.info)

        self.actions = BoxLayout(orientation="vertical", spacing=6, padding=(0, 0), size_hint_y=None, height=0, opacity=0)
        self.actions.disabled = True
        for title, fn in [("СИНХРОНИЗИРОВАТЬ И ОБУЧИТЬ", self.train), ("LIVE-ПРОГНОЗ", self.predict), ("ЦИКЛ САМООБУЧЕНИЯ", self.learn), ("ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ", self.resolve)]:
            btn = Button(text=title, size_hint_y=None, height=56)
            btn.bind(on_release=fn)
            self.actions.add_widget(btn)
        self.content.add_widget(self.actions)

    def toggle_menu(self, _):
        self.menu_open = not self.menu_open
        if self.menu_open:
            self.actions.height = len(self.actions.children) * 56 + max(0, len(self.actions.children) - 1) * 6
            self.actions.opacity = 1
            self.actions.disabled = False
            self.menu_button.text = "X"
        else:
            self.actions.opacity = 0
            self.actions.height = 0
            self.actions.disabled = True
            self.menu_button.text = "..."

    def worker(self, fn):
        self.info.text = "Работаю...\nНе закрывайте приложение."
        def w():
            try: result = fn()
            except Exception: result = "Ошибка:\n" + traceback.format_exc()
            Clock.schedule_once(lambda dt: self.show(result), 0)
        threading.Thread(target=w, daemon=True).start()
    def show(self, value): self.info.text = str(value)
    def train(self, _): self.worker(lambda: (lambda r: f"Обучение завершено.\nAccuracy: {r['accuracy']:.3f}\nBalanced: {r['balanced_accuracy']:.3f}\nМодель принята: {r['accepted']}")(self.engine.train_from_fresh()))
    def predict(self, _): self.worker(lambda: (lambda r: f"ПРОГНОЗ: {r['prediction']}\nЦена: {r['price']:.8g}\nSHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}")(self.engine.predict_and_store()))
    def learn(self, _): self.worker(lambda: (lambda z: f"Цикл завершён.\nПроверено: {z[0]}\nAccuracy: {z[1]['accuracy']:.3f}")(self.engine.learning_cycle()))
    def resolve(self, _): self.worker(lambda: f"Новых прогнозов проверено: {self.engine.resolve_pending()}")


class TraderApp(App):
    def build(self):
        root = Path(self.user_data_dir)
        cfg = load(Path(__file__).resolve().parent / "config.json")
        return UI(LearningEngine(root, KuCoin(cfg["symbol"]), cfg))


if __name__ == "__main__": TraderApp().run()
