# KuCoinSignalApp PRO

Rule-based KuCoin Futures signal scanner using the UTA V2 market API.

## Signal model
- 5m / 15m / 1h / 4h closed candles
- EMA 20 / 50 / 200
- RSI 14
- Correct MACD histogram (EMA12 - EMA26 minus EMA9 of MACD)
- Wilder-style ADX
- ATR-based risk levels
- Volume expansion
- 15m / 1h structure and breakout proximity
- Order-book imbalance as a small confirmation
- 5m open-interest delta
- Current funding rate as a small contrarian confirmation
- Separate LONG and SHORT scores
- WAIT unless score, score difference, and 4h+1h trend alignment pass the filters

The app uses public market data only and does not place orders.

KuCoin UTA V2 documentation recommends the current V2 endpoints for market data. Futures Klines are available through the UTA V2 Kline endpoint, and historical OI is available by interval. See the official KuCoin documentation for current limits and endpoint behavior.
