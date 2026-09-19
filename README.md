# SelfLearningTrader Ultimate V12

Android-only paper-trading market scanner for KuCoin USDT perpetuals.

## V12 fixes
- Correct KuCoin Futures candle parsing: `[time, open, high, low, close, volume, turnover]`.
- TOP-5 contains unique contracts only; one contract cannot occupy multiple slots.
- Scanner uses an isolated exchange/engine and never changes the user's selected coin.
- Scanner progress distinguishes real-candle candidates from request errors.
- Selected coin is explicitly shown in the UI; opening a TOP-5 candidate synchronizes the search/selection header.
- Manual coin search remains available for the full active-contract list.
- WAIT does not create a trading plan.
- Calculator and Cross/Isolated paper calculations retained.
- Portrait and landscape build configuration retained.

KuCoin's documented Futures Kline format is `[time, open, high, low, close, volume, turnover]`; the previous build incorrectly treated the high field as close, which could distort indicators and model outputs.
