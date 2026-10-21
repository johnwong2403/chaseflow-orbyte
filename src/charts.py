"""
Chart geometry for the dashboard.

The charts are plain inline SVG drawn by the template, so there is no
JavaScript chart library to load, nothing to break on a slow network, and
every bar and slice comes straight from the real invoice data. This module
only does the arithmetic: where each bar goes, how tall it is, where the
axis ticks sit.
"""

import math

SEVERITY_CLASSES = ["sev-0", "sev-1", "sev-2", "sev-3"]


def _step(max_value: float, is_count: bool) -> float:
    """Size of one y-axis interval (the axis always has 4 intervals)."""
    if is_count:
        return max(1, math.ceil(max_value / 4))
    if max_value <= 0:
        return 250
    raw = max_value / 4
    exponent = 10 ** math.floor(math.log10(raw))
    for multiplier in (1, 2, 2.5, 5, 10):
        if raw <= multiplier * exponent:
            return multiplier * exponent
    return 10 * exponent


def bar_chart(buckets: list, key: str, single_class: str = None, unit: str = "invoice", show_sub: bool = True) -> dict:
    """Geometry for a bar chart of the ageing buckets.

    buckets: [{"label", "count", "amount"}, ...]  (from data.ageing_summary)
    key:     "amount" (RM) or "count" (number of things)
    single_class: draw every bar in one colour class (e.g. "sev-0") instead of
                  the green-to-red severity scale
    unit:    what "count" counts, for the labels ("invoice", "reminder", ...)
    show_sub: second label line under each bar ("2 invoices · 53.7%")
    """
    is_count = key == "count"
    width, height = 520, 260
    left, right, top, bottom = 58, 14, 32, 52
    plot_w = width - left - right
    plot_h = height - top - bottom
    base = top + plot_h

    values = [b[key] for b in buckets]
    step = _step(max(values, default=0), is_count)
    y_max = step * 4

    ticks = []
    for i in range(5):
        value = step * i
        ticks.append({
            "label": f"{int(value)}" if is_count else f"{value:,.0f}",
            "y": round(base - (value / y_max) * plot_h, 1),
        })

    total = sum(values)
    slot = plot_w / max(len(buckets), 1)
    bar_w = slot * 0.5
    bars = []
    for i, b in enumerate(buckets):
        value = b[key]
        bar_h = (value / y_max) * plot_h if y_max else 0
        share = (value / total * 100) if total else 0
        count_text = f"{b['count']} {unit}" + ("" if b["count"] == 1 else "s")
        value_label = f"{value}" if is_count else f"RM {value:,.2f}"
        bars.append({
            "x": round(left + slot * i + (slot - bar_w) / 2, 1),
            "y": round(base - bar_h, 1),
            "w": round(bar_w, 1),
            "h": round(max(bar_h, 2), 1),  # keep a visible sliver for zero
            "cx": round(left + slot * i + slot / 2, 1),
            "cls": single_class or SEVERITY_CLASSES[i % len(SEVERITY_CLASSES)],
            "label": b["label"],
            "sub": f"{count_text} · {share:.1f}%" if show_sub else "",
            "value_label": value_label,
            "tip": (f"{b['label']}: RM {b['amount']:,.2f} across {count_text}" if key == "amount"
                    else f"{b['label']}: {count_text}"),
        })

    return {
        "width": width, "height": height, "left": left,
        "right": width - right, "base": base,
        "ticks": ticks, "bars": bars,
    }


def donut_segments(buckets: list, radius: int = 64) -> dict:
    """Stroke-dash values to draw the ageing mix as a donut (by RM amount)."""
    circumference = 2 * math.pi * radius
    total = sum(b["amount"] for b in buckets)
    segments, legend, used = [], [], 0.0
    for i, b in enumerate(buckets):
        share = (b["amount"] / total) if total else 0
        length = share * circumference
        cls = SEVERITY_CLASSES[i % len(SEVERITY_CLASSES)]
        if length > 0:
            segments.append({
                "cls": cls,
                "dash": f"{max(length - 2, 0.5):.2f} {circumference:.2f}",
                "offset": f"{-used:.2f}",
            })
        used += length
        legend.append({"cls": cls, "label": b["label"], "pct": f"{share * 100:.1f}"})
    return {
        "radius": radius,
        "circumference": round(circumference, 2),
        "segments": segments,
        "legend": legend,
        "has_data": total > 0,
    }