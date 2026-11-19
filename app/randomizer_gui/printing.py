"""Printable outputs: daily sheets (one page per date) and labels for cages, syringes or tubes.

Both draw on any QPagedPaintDevice, so the same code makes a PDF (QPdfWriter) or prints (QPrinter).
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextDocument, QColor

from randomizer.dates import daily_sheets


# ----------------------------------------------------------------------------- daily sheets
def daily_sheets_html(res, cal, blinded: bool, title: str) -> str:
    sheets = daily_sheets(res, cal, blinded)
    spec = res.spec
    per = spec.period_name
    parts = []
    for i, (d, df) in enumerate(sheets.items()):
        brk = ' style="page-break-before: always;"' if i else ""
        periods = ", ".join(f"{per} {k}" for k in sorted(set(df[per])))
        cols = [c for c in df.columns if c not in ("Fixed period",)]
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols) + "<th>Done</th><th>Initials</th>"
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "<td></td><td></td></tr>"
                       for row in df[cols].itertuples(index=False))
        parts.append(f"""
<div{brk}>
<p class="small">{html.escape(title)}{' · BLINDED' if blinded else ''}</p>
<h1>{d.strftime('%A %d %B %Y')}</h1>
<p class="small">{html.escape(periods)} · {len(df)} {html.escape(spec.noun(len(df) != 1))}</p>
<table width="100%" cellspacing="0" cellpadding="5"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</div>""")
    css = """
body { font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; font-size: 10pt; color: #111; }
h1 { font-size: 17pt; margin: 2px 0 2px 0; }
.small { color: #555; font-size: 9pt; margin: 0; }
table { border-collapse: collapse; margin-top: 10px; }
th { background: #eef0f3; text-align: left; border-bottom: 1px solid #999; font-size: 9pt; }
td { border-bottom: 1px solid #ccc; }
"""
    return f"<html><head><style>{css}</style></head><body>{''.join(parts)}</body></html>"


def _setup(device, page_size=QPageSize.A4, landscape=False):
    device.setPageSize(QPageSize(page_size))
    device.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    device.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)


def print_html(device, text: str):
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Segoe UI", 10))
    doc.setHtml(text)
    doc.print_(device)


def daily_sheets_pdf(res, cal, path: str, blinded: bool, title: str, letter=False):
    w = QPdfWriter(path)
    w.setTitle(f"{title} – daily sheets")
    w.setResolution(300)
    _setup(w, QPageSize.Letter if letter else QPageSize.A4)
    print_html(w, daily_sheets_html(res, cal, blinded, title))


# ----------------------------------------------------------------------------- labels
@dataclass
class LabelLayout:
    name: str
    page: QPageSize.PageSizeId
    cols: int
    rows: int
    width_mm: float
    height_mm: float
    left_mm: float
    top_mm: float
    hgap_mm: float
    vgap_mm: float


LAYOUTS = [
    LabelLayout("A4, 3 × 7 labels, 63.5 × 38.1 mm (e.g. Avery L7160)", QPageSize.A4, 3, 7, 63.5, 38.1, 7.2, 15.1, 2.5, 0),
    LabelLayout("A4, 3 × 8 labels, 70 × 37 mm (e.g. Avery 3474)", QPageSize.A4, 3, 8, 70, 37, 0, 0.5, 0, 0),
    LabelLayout("A4, 4 × 10 labels, 48.5 × 25.4 mm (e.g. Avery L4736)", QPageSize.A4, 4, 10, 48.5, 25.4, 8, 21.5, 0, 0),
    LabelLayout("Letter, 3 × 10 labels, 2.625 × 1 in (e.g. Avery 5160)", QPageSize.Letter, 3, 10, 66.7, 25.4, 4.8, 12.7, 3.2, 0),
]


def label_texts(res, cal, blinded: bool, per_period: bool) -> list[list[str]]:
    """Lines for each label: ID (+ group), period and date, treatment or code."""
    from randomizer.dates import dated_schedule, check
    spec = res.spec
    idc = spec.id_column
    if per_period:
        use_dates = cal is not None and not check(cal, res)
        df = dated_schedule(res, cal, blinded) if use_dates else __import__(
            "randomizer.export", fromlist=["long_format"]).long_format(res)
        df = df.sort_values([idc, spec.period_name], kind="stable")
        out = []
        for _, r in df.iterrows():
            line2 = f"{spec.period_name} {r[spec.period_name]}"
            if use_dates and r.get("Date") is not None:
                line2 += f" · {r['Date']:%a %d %b %Y}"
            treat = r["Code"] if blinded and "Code" in r else r["Treatment"]
            out.append([str(r[idc]), line2, str(treat)])
        return out
    # one label per subject with the whole sequence
    out = []
    for _, r in res.schedule.iterrows():
        seq = [str(r[c]) for c in res.period_columns]
        if blinded and res.codes:
            seq = [res.codes.get(x, x) for x in seq]
        groups = " · ".join(str(r[c]) for c in spec.strata if c in r)
        out.append([str(r[idc]) + (f"  ({groups})" if groups else ""), " – ".join(seq)])
    return out


def draw_labels(device, texts: list[list[str]], layout: LabelLayout, outline: bool = False):
    device.setPageSize(QPageSize(layout.page))
    device.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    p = QPainter(device)
    dpmm = device.logicalDpiX() / 25.4
    per_page = layout.cols * layout.rows
    big, small = QFont("Segoe UI"), QFont("Segoe UI")
    big.setBold(True)
    for i, lines in enumerate(texts):
        if i and i % per_page == 0:
            device.newPage()
        k = i % per_page
        r, c = divmod(k, layout.cols)
        x = (layout.left_mm + c * (layout.width_mm + layout.hgap_mm)) * dpmm
        y = (layout.top_mm + r * (layout.height_mm + layout.vgap_mm)) * dpmm
        rect = QRectF(x, y, layout.width_mm * dpmm, layout.height_mm * dpmm)
        if outline:
            p.setPen(QPen(QColor("#bbbbbb"), 0))
            p.drawRect(rect)
        inner = rect.adjusted(3 * dpmm, 2.5 * dpmm, -3 * dpmm, -2.5 * dpmm)
        n = len(lines)
        line_h = inner.height() / max(n, 1)
        big.setPixelSize(max(6, int(min(line_h * 0.62, 4.2 * dpmm))))
        small.setPixelSize(max(5, int(min(line_h * 0.5, 3.2 * dpmm))))
        p.setPen(QColor("#000000"))
        for j, text in enumerate(lines):
            p.setFont(big if j in (0, n - 1) else small)
            p.drawText(QRectF(inner.x(), inner.y() + j * line_h, inner.width(), line_h),
                       Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                       p.fontMetrics().elidedText(text, Qt.ElideRight, int(inner.width())))
    p.end()


def labels_pdf(texts, path: str, layout: LabelLayout, outline=True, title="Labels"):
    w = QPdfWriter(path)
    w.setTitle(title)
    w.setResolution(300)
    draw_labels(w, texts, layout, outline)
