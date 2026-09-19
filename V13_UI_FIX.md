# V13 UI fix

Fixed the Android layout issue visible on narrow screens:
- disabled unnecessary horizontal scrolling in the main screen;
- content width now follows the actual ScrollView viewport, not the root window width;
- calculator remains fully inside the viewport in portrait mode;
- calculator uses two columns only when the real viewport is wide enough;
- preserved vertical scrolling so the full calculator and results remain accessible;
- prevents oversized blank/scrollable content caused by a width mismatch.
