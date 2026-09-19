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
from core.calculator import calculate_position

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
        self.info.bind(width=lambda o,v:setattr(o,'text_size',(max(dp(100),v-dp(4)),None)))
        self.info.bind(texture_size=lambda o,v:setattr(o,'height',max(dp(120),v[1]+dp(20)))); self.content.add_widget(self.info)
        self.actions=BoxLayout(orientation='vertical',spacing=dp(6),size_hint_y=None,height=0,opacity=0); self.actions.disabled=True
        buttons=[('ОБУЧИТЬ ВЫБРАННУЮ',self.train),('LIVE-ПРОГНОЗ ВЫБРАННОЙ',self.predict),('СКАНИРОВАТЬ KUCOIN → TOP-5',self.scan),('ЦИКЛ САМООБУЧЕНИЯ',self.learn),('ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ',self.resolve)]
        for text,fn in buttons:
            b=Button(text=text,size_hint_y=None,height=dp(58)); b.bind(on_release=fn); self.actions.add_widget(b)
        self.content.add_widget(self.actions)
        self.results_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None,width=self.scroll.width); self.results_box.bind(width=lambda o,v:setattr(o,'size_hint_x',None)); self.results_box.bind(minimum_height=self.results_box.setter('height')); self.content.add_widget(self.results_box)
        self.calc_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None,width=self.scroll.width); self.calc_box.bind(width=lambda o,v:setattr(o,'size_hint_x',None)); self.calc_box.bind(minimum_height=self.calc_box.setter('height')); self.content.add_widget(self.calc_box)
        Window.bind(size=self._on_window_resize)
        Clock.schedule_once(lambda dt:self._on_window_resize(),.1)
        Clock.schedule_once(lambda dt:self.refresh_symbols(None),.2)

    def _on_window_resize(self, *args):
        # Keep every text block readable in both portrait and landscape.
        w=max(dp(220), self.width-dp(24))
        self.content.width=w
        self.info.width=w
        self.results_box.width=w
        self.calc_box.width=w
        for child in self.results_box.children:
            child.width=w
            if hasattr(child,'text_size'): child.text_size=(w-dp(20),None)
        for child in self.calc_box.children:
            if isinstance(child, Label) and child is not getattr(self,'calc_out',None):
                child.text_size=(max(dp(100),child.width-dp(4)),None)


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
        base=(f"{r['symbol']} [{r['exchange_symbol']}]\nПРОГНОЗ: {r['prediction']}\n"
              f"Вероятности: SHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}\n")
        if r['prediction']=='WAIT':
            return base+"\nТОРГОВЫЙ ВХОД НЕ ФОРМИРУЕТСЯ: модель выбрала WAIT.\n"+f"Горизонт: {r['horizon_bars']} x 5m\n\nСигнал сохранён для последующей проверки."
        return base+(f"\nРыночная зона входа: {r['entry']:.6g}\nБазовый SL: {r['sl']:.6g}\nTP1: {r['tp1']:.6g}\nTP2: {r['tp2']:.6g}\nTP3: {r['tp3']:.6g}\n"
                     f"Горизонт: {r['horizon_bars']} x 5m\n\nСигнал сохранён для последующей проверки.")

    def scan(self,_):
        self.results_box.clear_widgets(); self._scan_rows=[]; self._scan_seen=[]; self._scan_errors=0; self._scan_total=0
        self.info.text='LIVE-СКАНЕР: получаю рынок KuCoin и начинаю предварительный анализ...\nНе закрывайте приложение.'
        def progress(done,total,name,row,err,phase='PRESCAN'):
            def apply(_dt):
                if phase=='PRESCAN':
                    self._scan_total=total
                    if err: self._scan_errors+=1
                    self.info.text=(f'ПРЕДСКАНИРОВАНИЕ: {done}/{total}\n'
                                     f'Кандидатов: {len(self._scan_seen)} | Ошибок: {self._scan_errors}\n'
                                     f'После анализа рынка будут обучены модели для лучших кандидатов.')
                else:
                    if err: self._scan_errors+=1
                    if row:
                        self._scan_seen.append(row)
                        ranked=sorted(self._scan_seen,key=lambda r:(r.get('prediction')!='WAIT',r.get('edge_score',-9),r.get('quality',0),r.get('turnover24h',0)),reverse=True)[:5]
                        self._scan_rows=ranked
                        self.results_box.clear_widgets()
                        for rank,r in enumerate(ranked,1):
                            if r['prediction']=='WAIT':
                                txt=f'#{rank}  {r["symbol"]} | WAIT {r["p_wait"]:.0%}\nНет торгового входа'
                            else:
                                txt=(f'#{rank}  {r["symbol"]} | {r["prediction"]} | {max(r["p_short"],r["p_long"]):.0%}\n'
                                     f'Entry {r["entry"]:.6g}  SL {r["sl"]:.6g}  TP1 {r["tp1"]:.6g}')
                            b=Button(text=txt,size_hint_y=None,height=dp(82),halign='left',valign='middle')
                            b.bind(size=lambda o,v:setattr(o,'text_size',(max(dp(100),o.width-dp(20)),None)))
                            b.bind(on_release=lambda btn,x=r:self.open_candidate(x)); self.results_box.add_widget(b)
                    self.info.text=(f'ОБУЧЕНИЕ КАНДИДАТОВ: {done}/{total}\n'
                                    f'Успешно: {len(self._scan_seen)} | Ошибок: {self._scan_errors}\n'
                                    f'TOP-{min(5,len(self._scan_rows))} уже доступен выше.')
            Clock.schedule_once(apply,0)
        def done(result):
            if isinstance(result,str): self.show(result); return
            if not isinstance(result,tuple): self.show(str(result)); return
            rows,total,quick_count,errors=result
            ranked=sorted(rows,key=lambda r:(r.get('prediction')!='WAIT',r.get('edge_score',-9),r.get('quality',0),r.get('turnover24h',0)),reverse=True)[:5]
            self._scan_seen=rows; self._scan_rows=ranked
            self.info.text=(f'LIVE-СКАНЕР ЗАВЕРШЁН\n'
                            f'Рынок: {total} инструментов | Предсканировано: {quick_count} | Ошибок: {errors}\n'
                            f'TOP-{len(ranked)} сформирован из лучших кандидатов.')
        self.worker(lambda:self.engine.scan_all(progress=progress),done)

    def open_candidate(self,r):
        self.engine.set_symbol(r['contract']); self._last_prediction=r; self.show(self._prediction_text(r)); self.build_calculator(r)

    def build_calculator(self,r):
        self.calc_box.clear_widgets()
        title=Label(text='КАЛЬКУЛЯТОР ПОЗИЦИИ',font_size='18sp',size_hint_y=None,height=dp(38))
        self.calc_box.add_widget(title)
        grid=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        def add(name,widget):
            row=BoxLayout(orientation='horizontal',spacing=dp(5),size_hint_y=None,height=dp(48))
            lab=Label(text=name,size_hint_x=.42,halign='left',valign='middle')
            lab.bind(size=lambda o,v:setattr(o,'text_size',(v[0],None)))
            widget.size_hint_x=.58
            row.add_widget(lab); row.add_widget(widget); grid.add_widget(row)
        self.direction=Spinner(text=r.get('prediction') if r.get('prediction') in ('LONG','SHORT') else 'LONG',values=('LONG','SHORT'),size_hint_y=None,height=dp(46)); add('Направление',self.direction)
        self.leverage=Spinner(text='30',values=('1','2','3','5','10','20','30','50','75','100'),size_hint_y=None,height=dp(46)); add('Плечо x',self.leverage)
        self.margin_mode=Spinner(text='ISOLATED',values=('ISOLATED','CROSS'),size_hint_y=None,height=dp(46)); add('Маржа',self.margin_mode)
        self.balance=TextInput(text='100',input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('Полный баланс фьючерсов, USDT',self.balance)
        self.margin=TextInput(text='5',input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('Маржа позиции, USDT',self.margin)
        wait_mode=r.get('prediction')=='WAIT'
        entry_default='' if wait_mode else f"{r.get('entry',0):.10g}"
        self.entry=TextInput(text=entry_default,input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('Entry',self.entry)
        self.sl=TextInput(text='' if wait_mode else f"{r.get('sl',0):.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('SL',self.sl)
        self.tp1=TextInput(text='' if wait_mode else f"{r.get('tp1',0):.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('TP1',self.tp1)
        self.tp2=TextInput(text='' if wait_mode else f"{r.get('tp2',r.get('tp1',0)):.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('TP2',self.tp2)
        self.tp3=TextInput(text='' if wait_mode else f"{r.get('tp3',r.get('tp1',0)):.10g}",input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('TP3',self.tp3)
        self.mmr=TextInput(text='0.50',input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('MMR %, fallback',self.mmr)
        self.liqfee=TextInput(text='0.06',input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('Liquidation fee %, fallback',self.liqfee)
        self.fee=TextInput(text='0.06',input_filter='float',multiline=False,size_hint_y=None,height=dp(46)); add('Taker fee %, fallback',self.fee)
        self.calc_box.add_widget(grid)
        calc=Button(text='РАССЧИТАТЬ / ОБНОВИТЬ',size_hint_y=None,height=dp(56)); calc.bind(on_release=lambda *_:self.calculate(r)); self.calc_box.add_widget(calc)
        self.calc_out=Label(text='',font_size='15sp',halign='left',valign='top',size_hint_y=None)
        self.calc_out.bind(width=lambda o,v:setattr(o,'text_size',(max(dp(100),v-dp(4)),None)))
        self.calc_out.bind(texture_size=lambda o,v:setattr(o,'height',max(dp(120),v[1]+dp(18))))
        self.calc_box.add_widget(self.calc_out)
        back=Button(text='← НАЗАД К TOP-5',size_hint_y=None,height=dp(52)); back.bind(on_release=lambda *_:self.back_to_top()); self.calc_box.add_widget(back)
        widgets=(self.direction,self.leverage,self.margin_mode,self.balance,self.margin,self.entry,self.sl,self.tp1,self.tp2,self.tp3,self.mmr,self.liqfee,self.fee)
        for w in widgets:
            if isinstance(w,TextInput): w.bind(text=lambda *_:self.calculate(r))
            else: w.bind(text=lambda *_:self.calculate(r))
        self.calculate(r)
        Clock.schedule_once(lambda dt:self.scroll_to_calculator(),0.05)

    def scroll_to_calculator(self):
        self.scroll.scroll_y=0

    def calculate(self,r):
        try:
            if r.get('prediction')=='WAIT' and not self.entry.text.strip():
                self.calc_out.text=('МОДЕЛЬ: WAIT — торговый план не сформирован.\n\n'
                                    'Калькулятор не подставляет фиктивные Entry/SL/TP.\n'
                                    'Если хочешь проверить гипотетическую сделку, выбери LONG/SHORT и введи Entry, SL и TP1–TP3.')
                return
            direction=self.direction.text.upper()
            lev=float(self.leverage.text); bal=float(self.balance.text); margin=float(self.margin.text)
            entry=float(self.entry.text); sl=float(self.sl.text); tp1=float(self.tp1.text)
            tp2=float(self.tp2.text); tp3=float(self.tp3.text)
            mmr=float(self.mmr.text)/100; liq_fee=float(self.liqfee.text)/100; taker=float(self.fee.text)/100
            if direction=='LONG' and not (sl<entry<tp1<=tp2<=tp3): raise ValueError('LONG: SL < Entry < TP1 ≤ TP2 ≤ TP3')
            if direction=='SHORT' and not (sl>entry>tp1>=tp2>=tp3): raise ValueError('SHORT: SL > Entry > TP1 ≥ TP2 ≥ TP3')
            info=self.engine.exchange.contract_info()
            def rate(name,fallback):
                v=info.get(name)
                if v is None:return fallback
                try:return float(v)
                except:return fallback
            multiplier=rate('multiplier',1.0)
            api_mmr=rate('maintainMargin',mmr*100)/100
            api_fee=rate('takerFeeRate',taker*100)/100
            # Some KuCoin payloads expose rates already as decimals; normalize only if needed.
            if api_mmr>1: api_mmr/=100
            if api_fee>1: api_fee/=100
            mmr=api_mmr if api_mmr>0 else mmr; taker=api_fee if api_fee>=0 else taker
            c=calculate_position(entry,margin,lev,multiplier,direction,mmr,taker,liq_fee,bal,self.margin_mode.text,sl,tp1,tp2,tp3)
            liq=c['liquidation']; liq_txt=f'{liq:.10g}' if liq is not None and liq>0 else 'нет положительной оценки'
            dist='—' if c['liq_distance_pct'] is None else f"{c['liq_distance_pct']:.2%}"
            amr='—' if c['amr'] is None else f"{c['amr']:.2%}"
            cross_note=('Cross: это справочная цена. Реальная ликвидация KuCoin определяется account risk ratio и Mark Price; '
                        'при других Cross-позициях/ордерах результат изменится.') if self.margin_mode.text=='CROSS' else 'Isolated: расчёт по формуле KuCoin для USDT-M; MMR и liquidation fee зависят от risk tier.'
            self.calc_out.text=(f"Направление: {direction}\nКонтракт: {info.get('symbol',self.engine.exchange.futures_symbol)} | multiplier: {multiplier:g}\n"
                f"Номинал: {c['notional']:.6f} USDT | Контрактов: {c['qty']:.10g}\n"
                f"Маржа позиции: {margin:.6f} | Полный баланс: {bal:.6f} | x{lev:g} | {self.margin_mode.text}\n"
                f"Открывающая комиссия: {c['opening_fee']:.6f} USDT\n\n"
                f"Entry: {entry:.10g}\nSL: {sl:.10g}\nTP1: {tp1:.10g} | TP2: {tp2:.10g} | TP3: {tp3:.10g}\n\n"
                f"P/L SL после комиссий: {c['pnl_sl']:.6f} USDT\nP/L TP1 после комиссий: {c['pnl_tp1']:.6f} USDT\nP/L TP2 после комиссий: {c['pnl_tp2']:.6f} USDT\nP/L TP3 после комиссий: {c['pnl_tp3']:.6f} USDT\n"
                f"R/R до TP1: 1:{c['rr']:.2f}\n\n"
                f"Ликвидация (расчёт): {liq_txt}\nЗапас Entry → Liquidation: {dist}\nAMR Cross: {amr}\n"
                f"MMR: {mmr:.3%} | taker: {taker:.3%} | liquidation fee: {liq_fee:.3%}\n{cross_note}")
        except Exception as e:
            self.calc_out.text='Ошибка расчёта: '+str(e)

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
