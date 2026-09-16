import json, threading
from pathlib import Path
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from core.config import load
from core.exchange import KuCoin
from core.engine import LearningEngine

class UI(BoxLayout):
    def __init__(self,engine,**kw):
        super().__init__(orientation="vertical",padding=18,spacing=10,**kw)
        self.engine=engine
        self.info=Label(text="SelfLearningTrader Ultimate\nГотов.",font_size="18sp")
        self.add_widget(self.info)
        for title,fn in [
            ("СИНХРОНИЗИРОВАТЬ И ОБУЧИТЬ",self.train),
            ("LIVE-ПРОГНОЗ",self.predict),
            ("ЦИКЛ САМООБУЧЕНИЯ",self.learn),
            ("ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ",self.resolve)]:
            b=Button(text=title,size_hint_y=None,height=68);b.bind(on_press=fn);self.add_widget(b)

    def worker(self,fn):
        self.info.text="Работаю..."
        def w():
            try:r=fn()
            except Exception as e:r="Ошибка:\n"+str(e)
            Clock.schedule_once(lambda dt:self.show(r),0)
        threading.Thread(target=w,daemon=True).start()
    def show(self,x):self.info.text=str(x)
    def train(self,_):
        self.worker(lambda:(lambda r:f"Обучение завершено.\nAccuracy: {r['accuracy']:.3f}\nBalanced: {r['balanced_accuracy']:.3f}\nНовая модель принята: {r['accepted']}")(self.engine.train_from_fresh()))
    def predict(self,_):
        self.worker(lambda:(lambda r:f"ПРОГНОЗ: {r['prediction']}\nЦена: {r['price']:.8g}\nSHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}")(self.engine.predict_and_store()))
    def learn(self,_):
        self.worker(lambda:(lambda z:f"Цикл самообучения завершён.\nНовых примеров: {z[0]}\nAccuracy: {z[1]['accuracy']:.3f}")(self.engine.learning_cycle()))
    def resolve(self,_):
        self.worker(lambda:f"Новых прогнозов проверено: {self.engine.resolve_pending()}")

class TraderApp(App):
    def build(self):
        root=Path(self.user_data_dir); cfg=load(Path(__file__).resolve().parent/"config.json")
        ex=KuCoin(cfg["symbol"]); return UI(LearningEngine(root,ex,cfg))
if __name__=="__main__":TraderApp().run()
