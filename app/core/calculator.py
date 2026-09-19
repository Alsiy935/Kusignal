"""Paper futures calculator for KuCoin USDT-margined linear contracts."""

def fnum(v, name):
    try:
        x=float(v)
    except Exception as e:
        raise ValueError(f'{name}: неверное число') from e
    if x != x:
        raise ValueError(f'{name}: неверное число')
    return x


def calculate_position(entry, margin, leverage, multiplier=1.0, direction='LONG', mmr=0.005,
                       taker_fee=0.0006, liquidation_fee=0.0006, balance=0.0,
                       margin_mode='ISOLATED', sl=None, tp1=None, tp2=None, tp3=None):
    entry=fnum(entry,'Entry'); margin=fnum(margin,'Маржа'); leverage=fnum(leverage,'Плечо')
    multiplier=fnum(multiplier,'Multiplier'); mmr=fnum(mmr,'MMR'); taker_fee=fnum(taker_fee,'Taker fee')
    liquidation_fee=fnum(liquidation_fee,'Liquidation fee'); balance=fnum(balance,'Баланс')
    direction=str(direction).upper(); mode=str(margin_mode).upper()
    if entry<=0 or margin<=0 or leverage<=0 or multiplier<=0: raise ValueError('Entry, маржа, плечо и multiplier должны быть > 0')
    if balance<0: raise ValueError('Баланс не может быть отрицательным')
    if direction not in ('LONG','SHORT'): raise ValueError('Направление должно быть LONG или SHORT')
    if mode not in ('ISOLATED','CROSS'): raise ValueError('Маржа должна быть ISOLATED или CROSS')
    if mode=='CROSS' and balance<=0: raise ValueError('Для Cross укажи полный баланс фьючерсного счёта')

    side=1 if direction=='LONG' else -1
    notional=margin*leverage
    qty=notional/(entry*multiplier)
    opening_fee=notional*taker_fee

    def gross_pnl(px):
        return (float(px)-entry)*qty*multiplier*side
    def net_pnl(px):
        return gross_pnl(px)-opening_fee-abs(qty*float(px)*multiplier)*taker_fee

    out={'direction':direction,'mode':mode,'entry':entry,'margin':margin,'balance':balance,
         'leverage':leverage,'multiplier':multiplier,'notional':notional,'qty':qty,
         'opening_fee':opening_fee,'mmr':mmr,'taker_fee':taker_fee,'liquidation_fee':liquidation_fee,
         'gross_pnl':gross_pnl,'net_pnl':net_pnl}

    # KuCoin published isolated formula for USDT-margined linear contracts:
    # (Open Value - Position Margin) /
    # [Position Size * Multiplier * (1 - side*MMR - side*LiquidationFee)]
    denom_iso=qty*multiplier*(1-side*mmr-side*liquidation_fee)
    liq_iso=(notional-margin)/denom_iso if denom_iso else None

    # KuCoin cross liquidation is an account-level risk-ratio mechanism. The displayed
    # liquidation price is reference-only. For a single USDT-M position, use the
    # published AMR formula with the full cross-margin balance and Entry as the
    # calculator's current-Mark proxy.
    mark_value=entry*qty*multiplier
    if mode=='CROSS':
        amr=balance/abs(mark_value) if mark_value else 0.0
        denom_cross=1-side*mmr-side*taker_fee
        liq_cross=((mark_value-abs(mark_value)*amr)/denom_cross)/(qty*multiplier) if denom_cross and qty else None
    else:
        amr=None; liq_cross=None
    out.update({'liq_isolated':liq_iso,'liq_cross':liq_cross,'amr':amr,
                'liquidation':liq_iso if mode=='ISOLATED' else liq_cross,
                'liquidation_reference':mode=='CROSS'})

    if sl is not None:
        out['sl']=fnum(sl,'SL'); out['pnl_sl']=net_pnl(out['sl'])
    for key,val in (('tp1',tp1),('tp2',tp2),('tp3',tp3)):
        if val is not None:
            out[key]=fnum(val,key.upper()); out['pnl_'+key]=net_pnl(out[key])
    if 'sl' in out and 'tp1' in out:
        risk=abs(gross_pnl(out['sl'])); reward=abs(gross_pnl(out['tp1']))
        out['risk']=risk; out['reward_tp1']=reward; out['rr']=reward/risk if risk>0 else 0.0
    liq=out['liquidation']
    out['liq_distance_pct']=abs(entry-liq)/entry if liq is not None and liq>0 else None
    out['margin_share']=margin/balance if balance>0 else None
    return out
