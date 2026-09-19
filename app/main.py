from kivy.uix.widget import Widget
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
        super().__init__(orientation='vertical', padding=(dp(12),dp(8)), spacing=dp(6), **kw)
        self.engine=engine
        self._last_prediction=None; self._scan_rows=[]; self._detail_open=False; self._ui_scale=1.0
        self._symbols=[]; self._nav_mode='scanner'; self._log_open=False
        Window.fullscreen=False
        self._bg=(0.035,0.045,0.055,1); self._panel=(0.075,0.095,0.115,1); self._panel2=(0.10,0.125,0.15,1); self._accent=(0.03,0.55,1,1); self._text=(0.93,0.95,0.98,1)

        def style_button(b, accent=False):
            b.background_normal=''; b.background_down=''; b.background_color=self._accent if accent else self._panel2
            b.color=self._text; b.font_size='14sp'; b.border=(dp(1),dp(1),dp(1),dp(1));
            return b

        # Header: hamburger | title/subtitle | fullscreen | menu
        header=BoxLayout(size_hint_y=None,height=dp(62),spacing=dp(6))
        hamburger=style_button(Button(text='☰',size_hint_x=None,width=dp(50)),False); hamburger.bind(on_release=lambda *_: self.toggle_menu_panel())
        header.add_widget(hamburger)
        titles=BoxLayout(orientation='vertical',padding=(dp(4),dp(1)),spacing=0)
        self.title=Label(text='SelfLearningTrader Ultimate - V13',font_size='18sp',halign='left',valign='middle',color=self._text)
        self.title.bind(size=lambda o,v:setattr(o,'text_size',(v[0],None)))
        self.subtitle=Label(text='Сканер | Анализ | Прогноз | Самообучение',font_size='11sp',halign='left',valign='middle',color=(.62,.68,.75,1))
        self.subtitle.bind(size=lambda o,v:setattr(o,'text_size',(v[0],None)))
        titles.add_widget(self.title); titles.add_widget(self.subtitle); header.add_widget(titles)
        self.fullscreen_btn=style_button(Button(text='⛶',size_hint_x=None,width=dp(58)),False); self.fullscreen_btn.bind(on_release=self.toggle_fullscreen); header.add_widget(self.fullscreen_btn)
        self.menu=style_button(Button(text='⋮',size_hint_x=None,width=dp(58)),False); self.menu.bind(on_release=self.toggle); header.add_widget(self.menu)
        self._header=header; self.add_widget(header)

        # Search row
        selector=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(6))
        self.symbol_search=TextInput(text='',hint_text='Поиск монеты: BTC, ETH, SOL...',multiline=False,size_hint_x=1,font_size='16sp',padding=(dp(10),dp(10)),background_color=(.92,.92,.94,1),foreground_color=(.08,.08,.1,1),hint_text_color=(.35,.38,.42,1))
        self.symbol_search.bind(text=self.filter_symbols); selector.add_widget(self.symbol_search)
        refresh=style_button(Button(text='↻',size_hint_x=None,width=dp(58)),False); refresh.bind(on_release=self.refresh_symbols); selector.add_widget(refresh); self.add_widget(selector)

        # Filter chips
        chips=BoxLayout(size_hint_y=None,height=dp(40),spacing=dp(5))
        for txt,mode in [('Все','all'),('Избранные','fav'),('USDT-M','usdt'),('Только активные','active')]:
            b=style_button(Button(text=txt,size_hint_x=1), txt=='Все'); b.bind(on_release=lambda _,m=mode:self.set_filter(m)); chips.add_widget(b)
        self.add_widget(chips)

        self.selected_label=Label(text='Выбрано: —',font_size='14sp',halign='left',valign='middle',color=self._text,size_hint_y=None,height=dp(28))
        self.selected_label.bind(size=lambda o,v:setattr(o,'text_size',(max(dp(100),v[0]-dp(4)),None))); self.add_widget(self.selected_label)

        # Main scrolling area. It is the only scrollable region; header and bottom nav stay fixed.
        self.scroll=ScrollView(do_scroll_x=False,do_scroll_y=True,bar_width=dp(5),scroll_timeout=250)
        self.content=BoxLayout(orientation='vertical',size_hint_y=None,size_hint_x=1,spacing=dp(6),padding=(0,0,0,dp(10)))
        self.content.bind(minimum_height=self.content.setter('height')); self.scroll.add_widget(self.content); self.add_widget(self.scroll)
        self.symbol_results=BoxLayout(orientation='vertical',spacing=dp(4),size_hint_y=None,height=0); self.symbol_results.bind(minimum_height=self.symbol_results.setter('height')); self.content.add_widget(self.symbol_results)

        self.info=Label(text='Загрузка списка монет...',font_size='14sp',halign='left',valign='top',size_hint_y=None,color=self._text,padding=(dp(12),dp(10)))
        self.info.bind(width=lambda o,v:setattr(o,'text_size',(max(dp(100),v-dp(20)),None))); self.info.bind(texture_size=lambda o,v:setattr(o,'height',max(dp(115),v[1]+dp(20))))
        self.info.bind(pos=self._update_card_rect,size=self._update_card_rect)
        from kivy.graphics import Color, RoundedRectangle
        with self.info.canvas.before:
            Color(*self._panel); self._info_rect=RoundedRectangle(pos=self.info.pos,size=self.info.size,radius=[dp(10)])
        self.content.add_widget(self.info)

        self.actions=BoxLayout(orientation='vertical',spacing=dp(6),size_hint_y=None,height=0,opacity=0); self.actions.disabled=True
        buttons=[('ОБУЧИТЬ ВЫБРАННУЮ',self.train),('LIVE-ПРОГНОЗ ВЫБРАННОЙ',self.predict),('СКАНИРОВАТЬ KUCOIN → TOP-5',self.scan),('ЦИКЛ САМООБУЧЕНИЯ',self.learn),('ПРОВЕРИТЬ СТАРЫЕ ПРОГНОЗЫ',self.resolve)]
        for text,fn in buttons:
            b=style_button(Button(text=text,size_hint_y=None,height=dp(50)),False); b.bind(on_release=fn); self.actions.add_widget(b)
        self.content.add_widget(self.actions)

        self.results_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None,width=1); self.results_box.bind(minimum_height=self.results_box.setter('height')); self.content.add_widget(self.results_box)
        self.calc_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None,width=1); self.calc_box.bind(minimum_height=self.calc_box.setter('height')); self.content.add_widget(self.calc_box)

        # Stop / scan button
        self.stop_btn=style_button(Button(text='■   Стоп',size_hint_y=None,height=dp(54)),True); self.stop_btn.bind(on_release=self.stop_scan); self.content.add_widget(self.stop_btn)

        # Collapsible log area
        self.log_btn=style_button(Button(text='▤   Лог (последние события)                 ˅',size_hint_y=None,height=dp(50)),False); self.log_btn.bind(on_release=self.toggle_log); self.content.add_widget(self.log_btn)
        self.log_box=Label(text='Лог пока пуст.',font_size='13sp',halign='left',valign='top',color=(.72,.76,.82,1),size_hint_y=None,height=0,opacity=0,padding=(dp(10),dp(8)))
        self.log_box.bind(width=lambda o,v:setattr(o,'text_size',(max(dp(100),v-dp(18)),None))); self.content.add_widget(self.log_box)

        # Fixed bottom navigation
        nav=BoxLayout(size_hint_y=None,height=dp(64),spacing=dp(2),padding=(0,dp(3)))
        for txt,mode in [('⌗\nСканер','scanner'),('▥\nАнализ','analysis'),('♙\nМодель','model'),('⚙\nНастройки','settings')]:
            b=style_button(Button(text=txt,font_size='12sp'), mode=='scanner'); b.bind(on_release=lambda _,m=mode:self.bottom_nav(m)); nav.add_widget(b)
        self.add_widget(nav)

        Window.bind(size=self._on_window_resize)
        Clock.schedule_once(lambda dt:self._on_window_resize(),.1)
        Clock.schedule_once(lambda dt:self.refresh_symbols(None),.2)

    def _update_card_rect(self, *args):
        try: self._info_rect.pos=self.info.pos; self._info_rect.size=self.info.size
        except Exception: pass

    def set_filter(self,mode):
        self._filter_mode=mode; self.filter_symbols(self.symbol_search,self.symbol_search.text)

    def toggle_menu_panel(self):
        self.toggle(self.menu)

    def toggle_log(self,*_):
        self._log_open=not self._log_open
        if self._log_open:
            self.log_box.opacity=1; self.log_box.height=dp(110); self.log_btn.text='▤   Лог (последние события)                 ˄'
        else:
            self.log_box.opacity=0; self.log_box.height=0; self.log_btn.text='▤   Лог (последние события)                 ˅'

    def bottom_nav(self,mode):
        self._nav_mode=mode
        if mode=='scanner': self.scroll.scroll_y=1; return
        if mode=='analysis':
            if self._last_prediction: self.show(self._prediction_text(self._last_prediction)); self.scroll.scroll_y=0
            else: self.show('Анализ: сначала выбери монету и запусти LIVE-ПРОГНОЗ.'); self.scroll.scroll_y=0
        elif mode=='model':
            self.show('Модель: для выбранной монеты доступны обучение, LIVE-прогноз и цикл самообучения через меню ☰/⋮.')
            self.scroll.scroll_y=0
        elif mode=='settings':
            self.show('Настройки: управление действиями и параметрами калькулятора доступно через верхнее меню и выбранную монету.')
            self.scroll.scroll_y=0

    def stop_scan(self,*_):
        self.show('Запрошена остановка текущего сканирования. Уже завершённые результаты сохранены.'); self._detail_open=False

    def _on_window_resize(self, *args):
        w=max(dp(240), self.scroll.width-dp(2))
        self.content.width=w; self.info.width=w; self.results_box.width=w; self.calc_box.width=w; self.symbol_results.width=w
        self.scroll.do_scroll_x=False
        for child in self.results_box.children:
            child.width=w
            if hasattr(child,'text_size'): child.text_size=(max(dp(120),w-dp(20)),None)
        if hasattr(self,'calc_grid'): self._layout_calculator(w)

    def toggle_fullscreen(self, _):
        Window.fullscreen = False if Window.fullscreen else 'auto'
        Clock.schedule_once(lambda dt:self._on_window_resize(), .15)

    def _layout_calculator(self, w):
        grid=self.calc_grid
        # Landscape: two compact columns; portrait: one column.
        landscape=self.width >= self.height * 1.15
        grid.clear_widgets()
        fields=getattr(self,'_calc_fields',[])
        if landscape and w >= dp(620):
            grid.cols=2
            grid.rows=(len(fields)+1)//2
            grid.spacing=dp(7)
            for name,widget in fields:
                cell=BoxLayout(orientation='horizontal',spacing=dp(4),size_hint_y=None,height=dp(50))
                lab=Label(text=name,size_hint_x=.52,halign='left',valign='middle',font_size='13sp')
                lab.bind(size=lambda o,v:setattr(o,'text_size',(v[0],None)))
                widget.size_hint_x=.48
                cell.add_widget(lab); cell.add_widget(widget); grid.add_widget(cell)
        else:
            grid.cols=1
            grid.rows=len(fields)
            grid.spacing=dp(5)
            for name,widget in fields:
                row=BoxLayout(orientation='horizontal',spacing=dp(5),size_hint_y=None,height=dp(48))
                lab=Label(text=name,size_hint_x=.46,halign='left',valign='middle',font_size='13sp')
                lab.bind(size=lambda o,v:setattr(o,'text_size',(v[0],None)))
                widget.size_hint_x=.54
                row.add_widget(lab); row.add_widget(widget); grid.add_widget(row)
        Clock.schedule_once(lambda dt:self.calc_box.setter('height')(self.calc_box,self.calc_box.minimum_height),0)

    def toggle(self,_):
        if self.actions.disabled:
            self.actions.disabled=False; self.actions.opacity=1; self.actions.height=len(self.actions.children)*56; self.menu.text='×'
        else:
            self.actions.disabled=True; self.actions.opacity=0; self.actions.height=0; self.menu.text='⋮'

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
            items=self.engine.exchange.active_symbols()
            def apply(_dt):
                self._symbols=items
                self.info.text=f'KuCoin: найдено активных USDT-фьючерсов: {len(items)}\nВведите название монеты в поле поиска.'
                self.filter_symbols(self.symbol_search,self.symbol_search.text)
            Clock.schedule_once(apply,0)
        threading.Thread(target=f,daemon=True).start()

    def filter_symbols(self, _widget, value):
        if not hasattr(self,'_symbols') or not hasattr(self,'symbol_results'): return
        q=str(value or '').strip().upper().replace('-USDT','').replace('USDTM','')
        rows=[]
        for x in self._symbols:
            display=x['display'].upper()
            contract=x['contract'].upper()
            base=str(x.get('base','')).upper()
            if not q or q in display or q in contract or q in base:
                rows.append(x)
            if len(rows)>=20: break
        self.symbol_results.clear_widgets()
        if not rows:
            self.symbol_results.height=0
            return
        for x in rows:
            b=Button(text=f"{x['display']}  [{x['contract']}]    ☆",size_hint_y=None,height=dp(50),background_normal='',background_down='',background_color=self._panel2,color=self._text,font_size='15sp')
            b.bind(on_release=lambda btn,item=x:self.select_symbol(item))
            self.symbol_results.add_widget(b)
        self.symbol_results.height=len(rows)*dp(47)

    def select_symbol(self,item):
        self.engine.set_symbol(item['contract'])
        self.symbol_search.text=item['display']
        self.selected_label.text=f'Выбрано: {item["display"]} [{item["contract"]}]'
        self.symbol_results.clear_widgets(); self.symbol_results.height=0
        self.info.text=f'Выбрано: {item["display"]} [{item["contract"]}]\nМодель хранится отдельно для этого инструмента.'

    def train(self,_):
        self.worker(lambda:(lambda r:f"Обучение {self.engine.exchange.symbol} завершено.\nСтрок: {r['rows']}\nTrain: {r['train_rows']} | Test: {r['test_rows']}\nAccuracy: {r['accuracy']:.3f}\nBalanced: {r['balanced_accuracy']:.3f}\nМодель принята: {r['accepted']}")(self.engine.train_from_fresh()))

    def predict(self,_):
        def f(): return self.engine.predict_and_store()
        def done(r):
            if isinstance(r,str): self.show(r); return
            self._detail_open=True
            self._last_prediction=r
            self.selected_label.text=f'Анализ: {r["symbol"]} [{r["exchange_symbol"]}]'
            self.symbol_search.text=r.get('symbol',self.symbol_search.text)
            self.show(self._prediction_text(r)); self.build_calculator(r)
        self.worker(f,done)

    def _prediction_text(self,r):
        base=(f"{r['symbol']} [{r['exchange_symbol']}]\nПРОГНОЗ: {r['prediction']}\n"
              f"Вероятности: SHORT {r['p_short']:.1%} | WAIT {r['p_wait']:.1%} | LONG {r['p_long']:.1%}\n")
        if r['prediction']=='WAIT':
            return base+"\nТОРГОВЫЙ ВХОД НЕ ФОРМИРУЕТСЯ: модель выбрала WAIT.\n"+f"Горизонт: {r['horizon_bars']} x 5m\n\nСигнал сохранён для последующей проверки."
        return base+(f"\nРыночная зона входа: {r['entry']:.6g}\nБазовый SL: {r['sl']:.6g}\nTP1: {r['tp1']:.6g}\nTP2: {r['tp2']:.6g}\nTP3: {r['tp3']:.6g}\n"
                     f"Горизонт: {r['horizon_bars']} x 5m\n\nСигнал сохранён для последующей проверки.")

    def scan(self,_):
        self._detail_open=False
        self.results_box.clear_widgets(); self._scan_rows=[]; self._scan_seen=[]; self._scan_quick_ok=0; self._scan_errors=0; self._scan_total=0
        self.info.text='LIVE-СКАНЕР: получаю рынок KuCoin и начинаю предварительный анализ...\nНе закрывайте приложение.'
        def progress(done,total,name,row,err,phase='PRESCAN'):
            def apply(_dt):
                if self._detail_open:
                    return
                if phase=='PRESCAN':
                    self._scan_total=total
                    if err:
                        self._scan_errors+=1
                    else:
                        self._scan_quick_ok+=1
                    self.info.text=(f'ПРЕДСКАНИРОВАНИЕ: {done}/{total}\n'
                                     f'Свечи/кандидаты OK: {self._scan_quick_ok} | Ошибок: {self._scan_errors}\n'
                                     f'Сейчас формируется пул лучших кандидатов. Выбранная монета не меняется.')
                else:
                    if err:
                        self._scan_errors+=1
                    if row:
                        # Never allow one contract to occupy multiple TOP-5 slots.
                        self._scan_seen=[x for x in self._scan_seen if x.get('contract')!=row.get('contract')]
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
                            b=Button(text=txt,size_hint_y=None,height=dp(78),halign='left',valign='middle',background_normal='',background_down='',background_color=self._panel2,color=self._text,font_size='14sp')
                            b.bind(size=lambda o,v:setattr(o,'text_size',(max(dp(100),o.width-dp(20)),None)))
                            b.bind(on_release=lambda btn,x=dict(r):self.open_candidate(x)); self.results_box.add_widget(b)
                    self.info.text=(f'ПРОВЕРКА МОДЕЛЕЙ: {done}/{total}\n'
                                    f'Кандидатов с реальными свечами: {self._scan_quick_ok} | Ошибок: {self._scan_errors}\n'
                                    f'TOP-{min(5,len(self._scan_rows))} доступен выше. Можно нажать LIVE-ПРОГНОЗ выбранной монеты.')
            Clock.schedule_once(apply,0)
        def done(result):
            if self._detail_open:
                return
            if isinstance(result,str): self.show(result); return
            if not isinstance(result,tuple): self.show(str(result)); return
            rows,total,quick_count,errors=result
            unique={}
            for row in rows:
                unique.setdefault(row.get('contract'),row)
            ranked=sorted(unique.values(),key=lambda r:(r.get('prediction')!='WAIT',r.get('edge_score',-9),r.get('quality',0),r.get('turnover24h',0)),reverse=True)[:5]
            self._scan_seen=list(unique.values()); self._scan_rows=ranked
            self.info.text=(f'LIVE-СКАНЕР ЗАВЕРШЁН\n'
                            f'Рынок: {total} инструментов | Реальные свечи: {quick_count} | Ошибок: {errors}\n'
                            f'TOP-{len(ranked)} сформирован. Каждая монета в TOP-5 уникальна.')
        self.worker(lambda:self.engine.scan_all(progress=progress),done)

    def open_candidate(self,r):
        self._detail_open=True
        self.engine.set_symbol(r['contract'])
        self._last_prediction=dict(r)
        self.symbol_search.text=r.get('symbol',self.symbol_search.text)
        self.selected_label.text=f'Анализ: {r["symbol"]} [{r["exchange_symbol"]}]'
        self.show(self._prediction_text(r)); self.build_calculator(r)

    def build_calculator(self,r):
        self.calc_box.clear_widgets()
        title=Label(text='КАЛЬКУЛЯТОР ПОЗИЦИИ',font_size='18sp',size_hint_y=None,height=dp(38),halign='left',valign='middle')
        title.bind(size=lambda o,v:setattr(o,'text_size',(v[0],None)))
        self.calc_box.add_widget(title)
        grid=GridLayout(cols=1,spacing=dp(5),size_hint_y=None,size_hint_x=1,padding=(0,0,0,dp(2)))
        grid.bind(minimum_height=grid.setter('height'))
        self.calc_grid=grid
        def field(text, value='', filter_type='float'):
            return TextInput(text=value,input_filter=filter_type,multiline=False,size_hint_y=None,height=dp(46),padding=(dp(8),dp(8)))
        self.direction=Spinner(text=r.get('prediction') if r.get('prediction') in ('LONG','SHORT') else 'LONG',values=('LONG','SHORT'),size_hint_y=None,height=dp(46))
        self.leverage=Spinner(text='30',values=('1','2','3','5','10','20','30','50','75','100'),size_hint_y=None,height=dp(46))
        self.margin_mode=Spinner(text='ISOLATED',values=('ISOLATED','CROSS'),size_hint_y=None,height=dp(46))
        self.balance=field('100')
        self.margin=field('5')
        wait_mode=r.get('prediction')=='WAIT'
        self.entry=field('' if wait_mode else f"{r.get('entry',0):.10g}")
        self.sl=field('' if wait_mode else f"{r.get('sl',0):.10g}")
        self.tp1=field('' if wait_mode else f"{r.get('tp1',0):.10g}")
        self.tp2=field('' if wait_mode else f"{r.get('tp2',r.get('tp1',0)):.10g}")
        self.tp3=field('' if wait_mode else f"{r.get('tp3',r.get('tp1',0)):.10g}")
        self.mmr=field('0.50')
        self.liqfee=field('0.06')
        self.fee=field('0.06')
        self._calc_fields=[
            ('Направление',self.direction),('Плечо x',self.leverage),('Маржа',self.margin_mode),
            ('Полный баланс фьючерсов, USDT',self.balance),('Маржа позиции, USDT',self.margin),
            ('Entry',self.entry),('SL',self.sl),('TP1',self.tp1),('TP2',self.tp2),('TP3',self.tp3),
            ('MMR %, fallback',self.mmr),('Liquidation fee %, fallback',self.liqfee),('Taker fee %, fallback',self.fee)]
        self.calc_box.add_widget(grid)
        calc=Button(text='РАССЧИТАТЬ / ОБНОВИТЬ',size_hint_y=None,height=dp(56)); calc.bind(on_release=lambda *_:self.calculate(r)); self.calc_box.add_widget(calc)
        self.calc_out=Label(text='',font_size='15sp',halign='left',valign='top',size_hint_y=None)
        self.calc_out.bind(width=lambda o,v:setattr(o,'text_size',(max(dp(100),v-dp(8)),None)))
        self.calc_out.bind(texture_size=lambda o,v:setattr(o,'height',max(dp(120),v[1]+dp(18))))
        self.calc_box.add_widget(self.calc_out)
        back=Button(text='← НАЗАД К TOP-5',size_hint_y=None,height=dp(52)); back.bind(on_release=lambda *_:self.back_to_top()); self.calc_box.add_widget(back)
        widgets=(self.direction,self.leverage,self.margin_mode,self.balance,self.margin,self.entry,self.sl,self.tp1,self.tp2,self.tp3,self.mmr,self.liqfee,self.fee)
        for w in widgets:
            w.bind(text=lambda *_:self.calculate(r))
        self._layout_calculator(max(dp(240),self.scroll.width-dp(4)))
        self.calculate(r)
        Clock.schedule_once(lambda dt:self.scroll_to_calculator(),0.05)

    def scroll_to_calculator(self):
        self.scroll.scroll_y=0
        self.scroll.do_scroll_x=False

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
        self._detail_open=False
        self.calc_box.clear_widgets(); self.info.text='Выбери монету из TOP-5 выше или введи другую монету в поиск.'; self.scroll.scroll_y=1

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
