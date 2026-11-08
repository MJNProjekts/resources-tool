import html
from datetime import datetime


def num(n) -> str:
    """Game-style number: 2.33T, 87.24M, 1,234."""
    n = float(n or 0)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= div:
            return f"{n / div:.2f}{suf}"
    return f"{n:,.0f}"


def hours(h: float) -> str:
    if h < 1:
        return f"{max(h, 0) * 60:.0f} min"
    if h < 48:
        return f"{h:.1f} h"
    return f"{h / 24:.1f} d"


def clock(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%a %H:%M")


def esc(s) -> str:
    return html.escape(str(s))
