import threading
from pathlib import Path
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.metrics import dp
from kivy.core.window import Window
from core.config import load
from core.exchange import KuCoin
from core.engine import LearningEngine

class UI(BoxLayout):
    def __init__(self,engine,**kw):
        super().__init__(orientation='vertical',padding=(dp(12),dp(10)),spacing=dp(6),**kw)
        self.engine=engine; self._last_prediction=None; self._scan_rows=[]; Window.fullscreen=False
        header=BoxLayout(size_hint_y=None,height=dp(52))
        self.title=Label(text='SelfLearningTrader Ultimate',font_size='18sp'); header.add_widget(self.title)
        self.menu=Button(text='...',size_hint_x=None,width=dp(52)); self.menu.bind(on_release=self.toggle); header.add_widget(self.menu); self.add_widget(header)
        selector=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(6))
        self.symbol_spinner=Spinner(text=self.engine.exchange.symbol,values=(self.engine.exchange.symbol,),size_hint_x=.72)
        self.symbol_spinner.bind(text=self.select_symbol); selector.add_widget(self.symbol_spinner)
        refresh=Button(text='↻',size_hint_x=None,width=dp(52)); refresh.bind(on_release=self.refresh_symbols); selector.add_widget(refresh); self.add_widget(selector)
        self.scroll=ScrollView(do_scroll_x=False); self.content=BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(6)); self.content.bind(minimum_height=self.content.setter('height')); self.scroll.add_widget(self.content); self.add_widget(self.scroll)
        self.info=Label(text='Загрузка списка монет...',font_size='16sp',halign='left',valign='top',size_hint_y=None)
        self.info.bind(texture_size=lambda o,v:setattr(o,'height',max(dp(120),v[1]+dp(20)))); self.content.add_widget(self.info)
        self.actions=BoxLayout(orientation='vertical',spacing=dp(6),size_hint_y=None,height=0,opacity=0); self.actions.disabled=True
        buttons=[('ОБУЧИТЬ ВЫБРАННУЮ',self.train),('LIVE-ПРОГНОЗ ВЫБРАННОЙ',self.predict),('СКАНИРОВАТЬ KUCOIN → TOP-5',self.scan),('ЦИКЛ САМООБУЧЕНИЯ',self.learn),('ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ',self.resolve)]
        for text,fn in buttons:
            b=Button(text=text,size_hint_y=None,height=dp(58)); b.bind(on_release=fn); self.actions.add_widget(b)
        self.content.add_widget(self.actions)
        self.results_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None); self.results_box.bind(minimum_height=self.results_box.setter('height')); self.content.add_widget(self.results_box)
        self.calc_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None); self.content.add_widget(self.calc_box)
        Clock.schedule_once(lambda dt:self.refresh_symbols(None),.2)

    def toggle(self,_):
        if self.actions.disabled:
            self.actions.disabled=False; self.actions.opacity=1; self.actions.height=len(self.actions.children)*64; self.menu.text='X'
        else:
            self.actions.disabled=True; self.actions.opacity=0; self.actions.height=0; self.menu.text='...'

    def worker(self,fn,on_done=None):
        self.info.text='Работаю...\nНе закрывайте приложение.'
        def run():
            try:r=fn()
            except Exception as e:r='Ошибка: '+str(e)
            Clock.schedule_once(lambda dt:self._finish(r,on_done),0)
        threading.Thread(target=run,daemon=True).start()
    def _finish(self,r,on_done):
        if on_done:on_done(r)
        else:self.show(r)
    def show(self,r): self.info.text=str(r)

    def refresh_symbols(self,_):
        def f():
            items=self.engine.exchange.active_symbols(); values=tuple(x['display']+' ['+x['contract']+']' for x in items)
            def apply(_dt):
                self._symbols=items; self.symbol_spinner.values=values or (self.engine.exchange.symbol,); current=self.engine.exchange.futures_symbol
                for i,x in enumerate(items):
                    if x['contract']==current:self.symbol_spinner.text=values[i]; break
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
        def f(): return self.engine.predict_and_store()
        def done(r):
            if isinstance(r,str): self.show(r); return
            self._last_prediction=r; self.show(self._prediction_text(r)); self.build_calculator(r)
        self.worker(f,done)

    def _prediction_text(self,r):
        return (f"{r['symbol']} [{r['exchange_symbol']}]\nПРОГНОЗ: {r['prediction']}\n"
                f"Вероятности: SHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}\n\n"
                f"Рыночная зона входа: {r['entry']:.6g}\nБазовый SL: {r['sl']:.6g}\nTP1: {r['tp1']:.6g}\nTP2: {r['tp2']:.6g}\nTP3: {r['tp3']:.6g}\n"
                f"Горизонт: {r['horizon_bars']} x 5m\n\nСигнал сохранён для последующей проверки.")

    def scan(self,_):
        def f(): return self.engine.scan_all()
        def done(rows):
            self.results_box.clear_widgets(); self._scan_rows=[]
            if isinstance(rows,str): self.show(rows); return
            good=[r for r in rows if 'error' not in r]
            good.sort(key=lambda r:max(r['p_short'],r['p_long']),reverse=True); good=good[:5]; self._scan_rows=good
            self.info.text=f'LIVE-СКАНЕР: выбраны TOP-{len(good)} кандидатов из {len(rows)} инструментов. Нажми на монету для глубокого анализа.'
            for r in good:
                b=Button(text=f"{r['symbol']}  |  {r['prediction']}  |  {max(r['p_short'],r['p_long']):.0%}\nEntry {r['entry']:.6g}  SL {r['sl']:.6g}  TP1 {r['tp1']:.6g}",size_hint_y=None,height=dp(72))
                b.bind(on_release=lambda btn,x=r:self.open_candidate(x)); self.results_box.add_widget(b)
        self.worker(f,done)

    def open_candidate(self,r):
        self.engine.set_symbol(r['contract']); self._last_prediction=r; self.show(self._prediction_text(r)); self.build_calculator(r)

    def build_calculator(self,r):
        self.calc_box.clear_widgets()
        title=Label(text='КАЛЬКУЛЯТОР ПОЗИЦИИ',font_size='18sp',size_hint_y=None,height=dp(34)); self.calc_box.add_widget(title)
        grid=GridLayout(cols=2,spacing=dp(4),size_hint_y=None); grid.bind(minimum_height=grid.setter('height'))
        def add(name,widget): grid.add_widget(Label(text=name,size_hint_y=None,height=dp(42),halign='left')); grid.add_widget(widget)
        self.leverage=Spinner(text='30',values=('1','2','3','5','10','20','30','50','75','100'),size_hint_y=None,height=dp(42)); add('Плечо x',self.leverage)
        self.margin_mode=Spinner(text='ISOLATED',values=('ISOLATED','CROSS'),size_hint_y=None,height=dp(42)); add('Маржа',self.margin_mode)
        self.balance=TextInput(text='100',input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('Баланс фьючерсов, USDT',self.balance)
        self.margin=TextInput(text='5',input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('Маржа позиции, USDT',self.margin)
        self.entry=TextInput(text=f"{r['entry']:.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('Entry',self.entry)
        self.sl=TextInput(text=f"{r['sl']:.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('SL',self.sl)
        self.tp=TextInput(text=f"{r['tp1']:.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('TP1',self.tp)
        self.mmr=TextInput(text='0.50',input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('MMR %, для расчёта',self.mmr)
        self.liqfee=TextInput(text='0.06',input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('Liquidation fee %, для расчёта',self.liqfee)
        self.fee=TextInput(text='0.06',input_filter='float',multiline=False,size_hint_y=None,height=dp(42)); add('Taker fee %, для расчёта',self.fee)
        self.calc_box.add_widget(grid)
        calc=Button(text='РАССЧИТАТЬ',size_hint_y=None,height=dp(54)); calc.bind(on_release=lambda *_:self.calculate(r)); self.calc_box.add_widget(calc)
        self.calc_out=Label(text='',font_size='15sp',halign='left',valign='top',size_hint_y=None); self.calc_out.bind(texture_size=lambda o,v:setattr(o,'height',v[1]+dp(16))); self.calc_box.add_widget(self.calc_out)
        back=Button(text='← НАЗАД К TOP-5',size_hint_y=None,height=dp(48)); back.bind(on_release=lambda *_:self.back_to_top()); self.calc_box.add_widget(back)
        self.calculate(r)

    def calculate(self,r):
        try:
            lev=float(self.leverage.text); bal=float(self.balance.text); margin=float(self.margin.text)
            entry=float(self.entry.text); sl=float(self.sl.text); tp=float(self.tp.text)
            mmr=float(self.mmr.text)/100; liq_fee=float(self.liqfee.text)/100; taker=float(self.fee.text)/100
            if min(lev,bal,margin,entry)<=0: raise ValueError('параметры должны быть больше нуля')
            direction=r.get('prediction','LONG').upper()
            if direction not in ('LONG','SHORT'): direction='LONG'
            notional=margin*lev
            qty=notional/entry
            side=1 if direction=='LONG' else -1
            pnl_sl=(sl-entry)*qty*side
            pnl_tp=(tp-entry)*qty*side
            open_fee=notional*taker
            close_fee=abs(qty*tp)*taker
            net_sl=pnl_sl-open_fee-(abs(qty*sl)*taker)
            net_tp=pnl_tp-open_fee-close_fee
            rr=(abs(pnl_tp)/abs(pnl_sl)) if pnl_sl else 0.0

            # KuCoin USDT-margined linear-contract reference formulas.
            # Isolated: position margin is the only position collateral.
            if direction=='LONG':
                liq_iso=(notional-margin)/(qty*(1-mmr-liq_fee))
            else:
                liq_iso=(notional+margin)/(qty*(1+mmr+liq_fee))

            # Cross: with one modeled position, AMR = total cross margin / abs(mark value).
            # This is a reference price; actual liquidation is account-risk based.
            amr=bal/notional if notional else 0.0
            mark_value=side*notional
            denom=1-side*mmr-side*taker
            liq_cross=((mark_value-abs(mark_value)*amr)/denom)/(side*qty) if abs(denom)>1e-12 else None
            liq=liq_iso if self.margin_mode.text=='ISOLATED' else liq_cross
            liq_text='нет' if liq is None or liq<=0 else f'{liq:.10g}'
            dist_sl=abs(entry-sl)/entry if entry else 0
            dist_liq=abs(entry-liq)/entry if liq and liq>0 else 0
            risk_share=margin/bal if bal else 0
            self.calc_out.text=(
                f"Направление: {direction}\nНоминал позиции: {notional:.6f} USDT\nКоличество: {qty:.10g}\n"
                f"Маржа: {margin:.6f} USDT | Баланс: {bal:.6f} USDT | x{lev:g}\n\n"
                f"Entry: {entry:.10g}\nSL: {sl:.10g}  ({dist_sl:.2%} от Entry)\nTP1: {tp:.10g}\n\n"
                f"Убыток до SL: {pnl_sl:.6f} USDT\nПрибыль до TP1: {pnl_tp:.6f} USDT\n"
                f"После ориентировочных taker-комиссий: SL {net_sl:.6f} USDT | TP1 {net_tp:.6f} USDT\n"
                f"R/R: 1:{rr:.2f}\n\n"
                f"Ликвидация ({self.margin_mode.text}): {liq_text}\n"
                f"Запас Entry → Liquidation: {dist_liq:.2%}\n"
                f"Маржа / баланс: {risk_share:.2%}\n"
                f"MMR: {mmr:.3%} | liquidation fee: {liq_fee:.3%} | taker fee: {taker:.3%}\n\n"
                "Для Cross это справочная цена: фактическая ликвидация зависит от риска всего аккаунта, других позиций и ордеров.\n"
                "Для точного значения перед сделкой нужно сверять параметры конкретного контракта и Mark Price KuCoin."
            )
        except Exception as e: self.calc_out.text='Ошибка расчёта: '+str(e)

    def back_to_top(self):
        self.calc_box.clear_widgets(); self.info.text='Выбери монету из TOP-5 выше.'; self.scroll.scroll_y=1

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
