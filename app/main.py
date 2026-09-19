import threading
from pathlib import Path
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.metrics import dp
from kivy.core.window import Window
from core.config import load
from core.exchange import KuCoin
from core.engine import LearningEngine

class UI(BoxLayout):
    def __init__(self,engine,**kw):
        super().__init__(orientation='vertical',padding=(dp(12),dp(10)),spacing=dp(6),**kw)
        self.engine=engine; Window.fullscreen=False
        header=BoxLayout(size_hint_y=None,height=dp(52))
        self.title=Label(text='SelfLearningTrader Ultimate',font_size='18sp'); header.add_widget(self.title)
        self.menu=Button(text='...',size_hint_x=None,width=dp(52)); self.menu.bind(on_release=self.toggle); header.add_widget(self.menu); self.add_widget(header)

        selector=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(6))
        self.symbol_spinner=Spinner(text=self.engine.exchange.symbol,values=(self.engine.exchange.symbol,),size_hint_x=.72)
        self.symbol_spinner.bind(text=self.select_symbol); selector.add_widget(self.symbol_spinner)
        refresh=Button(text='↻',size_hint_x=None,width=dp(52)); refresh.bind(on_release=self.refresh_symbols); selector.add_widget(refresh)
        self.add_widget(selector)

        self.scroll=ScrollView(do_scroll_x=False); self.content=BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(6)); self.content.bind(minimum_height=self.content.setter('height')); self.scroll.add_widget(self.content); self.add_widget(self.scroll)
        self.info=Label(text='Загрузка списка монет...',font_size='16sp',halign='left',valign='top',size_hint_y=None)
        self.info.bind(texture_size=lambda o,v:setattr(o,'height',max(dp(160),v[1]+dp(20)))); self.content.add_widget(self.info)
        self.actions=BoxLayout(orientation='vertical',spacing=dp(6),size_hint_y=None,height=0,opacity=0); self.actions.disabled=True
        buttons=[('ОБУЧИТЬ ВЫБРАННУЮ',self.train),('LIVE-ПРОГНОЗ ВЫБРАННОЙ',self.predict),('СКАНИРОВАТЬ ВСЕ KUCOIN',self.scan),('ЦИКЛ САМООБУЧЕНИЯ',self.learn),('ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ',self.resolve)]
        for text,fn in buttons:
            b=Button(text=text,size_hint_y=None,height=dp(58)); b.bind(on_release=fn); self.actions.add_widget(b)
        self.content.add_widget(self.actions)
        Clock.schedule_once(lambda dt:self.refresh_symbols(None),.2)

    def toggle(self,_):
        if self.actions.disabled:
            self.actions.disabled=False; self.actions.opacity=1; self.actions.height=len(self.actions.children)*64; self.menu.text='X'
        else:
            self.actions.disabled=True; self.actions.opacity=0; self.actions.height=0; self.menu.text='...'

    def worker(self,fn):
        self.info.text='Работаю...\nНе закрывайте приложение.'
        def run():
            try:r=fn()
            except Exception as e:r='Ошибка: '+str(e)
            Clock.schedule_once(lambda dt:self.show(r),0)
        threading.Thread(target=run,daemon=True).start()

    def show(self,r): self.info.text=str(r)

    def refresh_symbols(self,_):
        def f():
            items=self.engine.exchange.active_symbols()
            values=tuple(x['display']+' ['+x['contract']+']' for x in items)
            def apply(_dt):
                self._symbols=items
                self.symbol_spinner.values=values or (self.engine.exchange.symbol,)
                current=self.engine.exchange.futures_symbol
                for i,x in enumerate(items):
                    if x['contract']==current:
                        self.symbol_spinner.text=values[i]; break
                self.info.text=f'KuCoin: найдено активных USDT-фьючерсов: {len(items)}\nВыбрано: {self.engine.exchange.symbol}'
            Clock.schedule_once(apply,0)
        threading.Thread(target=f,daemon=True).start()

    def select_symbol(self,_,value):
        if not hasattr(self,'_symbols'): return
        for x in self._symbols:
            if value==x['display']+' ['+x['contract']+']':
                self.engine.set_symbol(x['contract']); self.info.text=f'Выбрано: {x["display"]}\nМодель хранится отдельно для этого инструмента.'; return

    def train(self,_):
        self.worker(lambda:(lambda r:f"Обучение {self.engine.exchange.symbol} завершено.\nСтрок: {r['rows']}\nTrain: {r['train_rows']} | Test: {r['test_rows']}\nAccuracy: {r['accuracy']:.3f}\nBalanced: {r['balanced_accuracy']:.3f}\nМодель принята: {r['accepted']}")(self.engine.train_from_fresh()))

    def predict(self,_):
        def f():
            r=self.engine.predict_and_store()
            return (f"{r['symbol']} [{self.engine.exchange.futures_symbol}]\nПРОГНОЗ: {r['prediction']}\nВероятности: SHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}\n\nВход: {r['entry']:.6g}\nSL: {r['sl']:.6g}\nTP1: {r['tp1']:.6g}\nTP2: {r['tp2']:.6g}\nTP3: {r['tp3']:.6g}\nГоризонт: {r['horizon_bars']} x 5m\n\nСигнал сохранён для последующей проверки.")
        self.worker(f)

    def scan(self,_):
        def f():
            rows=self.engine.scan_all()
            good=[r for r in rows if 'error' not in r]
            good.sort(key=lambda r:max(r['p_short'],r['p_long']),reverse=True)
            lines=[f'СКАНИРОВАНИЕ KUCOIN: {len(rows)} инструментов',f'Готовых прогнозов: {len(good)}','']
            for r in good:
                lines.append(f"{r['symbol']}: {r['prediction']} | S {r['p_short']:.0%} / W {r['p_wait']:.0%} / L {r['p_long']:.0%} | Entry {r['entry']:.6g} | SL {r['sl']:.6g} | TP1 {r['tp1']:.6g}")
            errors=[r for r in rows if 'error' in r]
            if errors:
                lines += ['',f'Ошибок: {len(errors)}']
                lines += [f"{r.get('symbol',r.get('contract','?'))}: {r['error']}" for r in errors[:10]]
            return '\n'.join(lines)
        self.worker(f)

    def learn(self,_):
        def f():
            z=self.engine.learning_cycle(); live='—' if z[2]['live_accuracy'] is None else f"{z[2]['live_accuracy']:.1%}"
            return f"Цикл самообучения {self.engine.exchange.symbol} завершён.\nНовых результатов: {z[0]}\nОбучающих строк: {z[1]['rows']}\nBalanced: {z[1]['balanced_accuracy']:.3f}\nПроверено LIVE: {z[2]['resolved']}\nПравильных LIVE: {z[2]['correct']}\nLIVE accuracy: {live}"
        self.worker(f)

    def resolve(self,_): self.worker(lambda:f"Новых прогнозов проверено: {self.engine.resolve_pending()}")

class TraderApp(App):
    def build(self):
        cfg=load(Path(__file__).resolve().parent/'config.json'); return UI(LearningEngine(Path(self.user_data_dir),KuCoin(cfg['symbol']),cfg))

if __name__=='__main__': TraderApp().run()
