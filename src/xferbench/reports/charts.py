"""Inline, dependency-free SVG charts. Every label is escaped."""

from __future__ import annotations

import math

from markupsafe import Markup, escape

VIOLET = "#a78bfa"
MAGENTA = "#f472d0"
MUTED = "#a9a6b8"
GRID = "#3a3b46"
TEXT = "#ecebf4"
SERIES = {"PAIR0-E": VIOLET, "PAIR0-N": MAGENTA}


def _fmt(v: float, pct: bool) -> str:
    return f"{v * 100:.1f}%" if pct else f"{v:.3g}"


def grouped_hbar(
    title: str,
    labels: list[str],
    series: dict[str, list[float | None]],
    *,
    pct: bool = True,
    diverging: bool = False,
    width: int = 760,
) -> Markup:
    """Horizontal grouped bars; None values are drawn as an explicit N/A marker."""
    n_series = max(len(series), 1)
    bar_h, gap = 12, 10
    row_h = n_series * bar_h + gap
    left, right, top = 270, 70, 30
    height = top + row_h * len(labels) + 30
    vals = [abs(v) for vs in series.values() for v in vs if v is not None] or [1.0]
    vmax = max(vals) * 1.05 or 1.0
    plot_w = width - left - right
    zero_x = left + (plot_w / 2 if diverging else 0)
    scale = (plot_w / 2 if diverging else plot_w) / vmax
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" class="chart">',
        f"<title>{escape(title)}</title>",
    ]
    for t in range(5):
        frac = t / 4
        for sign in (-1, 1) if diverging else (1,):
            x = zero_x + sign * frac * (plot_w / 2 if diverging else plot_w)
            parts.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 24}" stroke="{GRID}"/>')
            parts.append(
                f'<text x="{x:.1f}" y="{height - 8}" fill="{MUTED}" font-size="11" text-anchor="middle">'
                f"{escape(_fmt(sign * frac * vmax, pct))}</text>"
            )
    parts.append(f'<line x1="{zero_x:.1f}" y1="{top - 8}" x2="{zero_x:.1f}" y2="{height - 24}" stroke="{MUTED}"/>')
    for i, lab in enumerate(labels):
        y0 = top + i * row_h
        parts.append(
            f'<text x="{left - 8}" y="{y0 + row_h / 2:.1f}" fill="{TEXT}" font-size="12" '
            f'text-anchor="end" dominant-baseline="middle">{escape(lab[:42])}</text>'
        )
        for j, (name, vs) in enumerate(series.items()):
            v = vs[i]
            y = y0 + j * bar_h
            color = SERIES.get(name, VIOLET if j == 0 else MAGENTA)
            if v is None:
                parts.append(
                    f'<text x="{zero_x + 4:.1f}" y="{y + bar_h - 2}" fill="{MUTED}" font-size="11">N/A '
                    f"({escape(name)})</text>"
                )
                continue
            w = abs(v) * scale
            x = zero_x - w if (diverging and v < 0) else zero_x
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{max(w, 1):.1f}" height="{bar_h - 2}" fill="{color}">'
                f"<title>{escape(lab)} {escape(name)}: {escape(_fmt(v, pct))}</title></rect>"
            )
            tx = (x - 4) if (diverging and v < 0) else (x + w + 4)
            anchor = "end" if (diverging and v < 0) else "start"
            parts.append(
                f'<text x="{tx:.1f}" y="{y + bar_h - 3}" fill="{TEXT}" font-size="10" '
                f'text-anchor="{anchor}">{escape(_fmt(v, pct))}</text>'
            )
    parts.append("</svg>")
    return Markup("".join(parts))


def line_chart(
    title: str,
    x_labels: list[str],
    series: dict[str, list[float | None]],
    *,
    pct: bool = True,
    width: int = 760,
    height: int = 300,
) -> Markup:
    left, right, top, bottom = 60, 190, 20, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    vals = [v for vs in series.values() for v in vs if v is not None] or [1.0]
    vmax = max(vals) * 1.1 or 1.0
    palette = [VIOLET, MAGENTA, "#7dd3fc", "#fcd34d", "#86efac", "#fca5a5", "#c4b5fd", "#f9a8d4"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" class="chart">',
        f"<title>{escape(title)}</title>",
    ]
    nx = max(len(x_labels) - 1, 1)
    for t in range(5):
        y = top + plot_h - t / 4 * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{GRID}"/>')
        parts.append(
            f'<text x="{left - 6}" y="{y:.1f}" fill="{MUTED}" font-size="11" text-anchor="end" '
            f'dominant-baseline="middle">{escape(_fmt(t / 4 * vmax, pct))}</text>'
        )
    for i, lab in enumerate(x_labels):
        x = left + i / nx * plot_w
        parts.append(
            f'<text x="{x:.1f}" y="{height - 18}" fill="{MUTED}" font-size="11" text-anchor="middle">'
            f"{escape(lab)}</text>"
        )
    families: dict[str, int] = {}
    for k, (name, vs) in enumerate(series.items()):
        family = name.replace(" PAIR0-E", "").replace(" PAIR0-N", "")
        color = palette[families.setdefault(family, len(families)) % len(palette)]
        dash = ' stroke-dasharray="5 3"' if "PAIR0-N" in name else ""
        pts = [(left + i / nx * plot_w, top + plot_h - (v / vmax) * plot_h) for i, v in enumerate(vs) if v is not None]
        if len(pts) > 1:
            d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
        for (x, y), v in zip(pts, [v for v in vs if v is not None], strict=True):
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"><title>{escape(name)}: '
                f"{escape(_fmt(v, pct))}</title></circle>"
            )
        ly = top + 12 + k * 16
        parts.append(
            f'<line x1="{left + plot_w + 12}" y1="{ly}" x2="{left + plot_w + 30}" y2="{ly}" '
            f'stroke="{color}" stroke-width="2"{dash}/>'
        )
        parts.append(
            f'<text x="{left + plot_w + 34}" y="{ly}" fill="{TEXT}" font-size="11" '
            f'dominant-baseline="middle">{escape(name[:26])}</text>'
        )
    parts.append("</svg>")
    return Markup("".join(parts))


def scatter(
    title: str,
    points: list[tuple[str, float, float]],
    x_label: str,
    y_label: str,
    *,
    width: int = 760,
    height: int = 320,
    empty_text: str = "No rankable points",
) -> Markup:
    left, right, top, bottom = 70, 30, 20, 50
    plot_w, plot_h = width - left - right, height - top - bottom
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" class="chart">',
        f"<title>{escape(title)}</title>",
    ]
    if not points:
        parts.append(
            f'<text x="{width / 2}" y="{height / 2}" fill="{MUTED}" text-anchor="middle">{escape(empty_text)}'
            "</text></svg>"
        )
        return Markup("".join(parts))
    xs = [max(p[1], 1e-4) for p in points]
    lx_min, lx_max = math.log10(min(xs)) - 0.2, math.log10(max(xs)) + 0.2
    ys = [p[2] for p in points]
    y_min, y_max = min(ys) * 0.95, max(ys) * 1.05
    y_span = (y_max - y_min) or 1.0
    for t in range(5):
        y = top + plot_h - t / 4 * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{GRID}"/>')
        parts.append(
            f'<text x="{left - 6}" y="{y:.1f}" fill="{MUTED}" font-size="11" text-anchor="end" '
            f'dominant-baseline="middle">{escape(_fmt(y_min + t / 4 * y_span, True))}</text>'
        )
        lx = lx_min + t / 4 * (lx_max - lx_min)
        x = left + t / 4 * plot_w
        parts.append(
            f'<text x="{x:.1f}" y="{height - 28}" fill="{MUTED}" font-size="11" text-anchor="middle">'
            f"{escape(f'{10**lx:.3g}s')}</text>"
        )
    parts.append(
        f'<text x="{left + plot_w / 2}" y="{height - 8}" fill="{MUTED}" font-size="12" '
        f'text-anchor="middle">{escape(x_label)}</text>'
    )
    parts.append(
        f'<text x="14" y="{top + plot_h / 2}" fill="{MUTED}" font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 14 {top + plot_h / 2})">{escape(y_label)}</text>'
    )
    for lab, xv, yv in points:
        x = left + (math.log10(max(xv, 1e-4)) - lx_min) / (lx_max - lx_min) * plot_w
        y = top + plot_h - (yv - y_min) / y_span * plot_h
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{VIOLET}" stroke="{MAGENTA}">'
            f"<title>{escape(lab)}: {escape(_fmt(yv, True))}, {escape(f'{xv:.3g}')}s</title></circle>"
        )
        parts.append(f'<text x="{x + 7:.1f}" y="{y - 6:.1f}" fill="{TEXT}" font-size="10">{escape(lab[:24])}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))
