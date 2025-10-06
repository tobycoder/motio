# jaarplanning.py
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from app.griffie import bp
import pandas as pd
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
from dateutil.parser import parse as dt_parse

REQUIRED_COLS = [
    "onderwerp",
    "omschrijving",
    "pfh code",
    "ontstaans datum",
    "oorspronkelijke planning",
    "huidige planning",
]

# Kleuren (hex) voor Excel achtergrondvulling (openpyxl)
COLOR_NEXT_1 = "FFFDE68A"  # zacht geel
COLOR_NEXT_2 = "FFA7F3D0"  # zacht groen
COLOR_NEXT_3 = "FFBFDBFE"  # zacht blauw
COLOR_LATER  = "FFE5E7EB"  # lichtgrijs

# ——— Helpers: triaalbepaling ———
def month_to_triaal(month: int) -> int:
    # T1: 1-4, T2: 5-8, T3: 9-12
    if 1 <= month <= 4:
        return 1
    elif 5 <= month <= 8:
        return 2
    else:
        return 3

def triaal_label(year: int, month: int) -> str:
    return f"T{month_to_triaal(month)} {year}"

def normalize_to_year_month(val):
    """
    Probeert waarde uit 'Huidige planning' om te zetten naar (year, month).
    Ondersteunt:
      - echte datumwaarden
      - tekst met NL maandnamen ('maart 2026', 'sep 2025')
      - triaalnotatie 'T2 2025'
      - losse 'YYYY-MM' / 'YYYY' / 'MM-YYYY'
    Valt terug op None bij mislukken.
    """
    if pd.isna(val):
        return None

    # Reeds datetime?
    if isinstance(val, (pd.Timestamp, datetime)):
        dt = pd.to_datetime(val, errors="coerce")
        if pd.notna(dt):
            return dt.year, dt.month

    s = str(val).strip()

    # Tn YYYY
    m = re.match(r"^[Tt]\s?([123])\s+(\d{4})$", s)
    if m:
        t = int(m.group(1))
        y = int(m.group(2))
        # Koppel T1->jan, T2->mei, T3->sep (eerste maand van triaal)
        month = {1: 1, 2: 5, 3: 9}[t]
        return y, month

    # Probeer generieke datumparser (met dag=1 fallback)
    try:
        dt = dt_parse(s, dayfirst=True, default=datetime(1900, 1, 1))
        if dt.year != 1900:  # parser vond iets bruikbaars
            return dt.year, dt.month
    except Exception:
        pass

    # NL maandnamen grofweg mappen (als parser faalt)
    nl_months = {
        "jan": 1, "januari": 1,
        "feb": 2, "februari": 2,
        "mrt": 3, "maart": 3,
        "apr": 4, "april": 4,
        "mei": 5,
        "jun": 6, "juni": 6,
        "jul": 7, "juli": 7,
        "aug": 8, "augustus": 8,
        "sep": 9, "sept": 9, "september": 9,
        "okt": 10, "oktober": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    parts = re.findall(r"[A-Za-z]+|\d{4}", s.lower())
    # Zoek maand + jaar
    year = None
    month = None
    for p in parts:
        if p.isdigit() and len(p) == 4:
            year = int(p)
        elif p in nl_months:
            month = nl_months[p]
    if year and month:
        return year, month

    # 'YYYY-MM' / 'MM-YYYY'
    m2 = re.match(r"^(\d{4})[-/](\d{1,2})$", s)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    m3 = re.match(r"^(\d{1,2})[-/](\d{4})$", s)
    if m3:
        return int(m3.group(2)), int(m3.group(1))

    return None

def compute_next_three_triaal_labels(now_dt: datetime):
    """Eerstvolgende triaal = waarin we nu zitten (inclusief huidige), plus de 2 daaropvolgende."""
    y, m = now_dt.year, now_dt.month
    t = month_to_triaal(m)
    labels = [f"T{t} {y}"]
    # Verschuif twee keer 4 maanden (naar volgende trialen)
    for _ in range(2):
        if t == 1:
            t = 2
        elif t == 2:
            t = 3
        else:
            t = 1
            y += 1
        labels.append(f"T{t} {y}")
    return labels  # [nu, +1, +2]

def color_for_label(label, next_labels):
    if label == next_labels[0]:
        return COLOR_NEXT_1
    if label == next_labels[1]:
        return COLOR_NEXT_2
    if label == next_labels[2]:
        return COLOR_NEXT_3
    return COLOR_LATER

# ——— Route: upload & resultaat ———
@bp.route("/jaarplanning", methods=["GET", "POST"])
def jaarplanning():
    if request.method == "GET":
        return render_template("griffie/jaarplanning.html")

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Kies een Excel-bestand (.xlsx).", "error")
        return redirect(url_for("griffie.jaarplanning"))

    filename = secure_filename(file.filename)
    try:
        # Lees Excel
        df_raw = pd.read_excel(file, dtype=str)  # lees alles als string; we normaliseren zelf
        # Normaliseer kolomnamen
        col_map = {c: c.strip() for c in df_raw.columns}
        df_raw.rename(columns=col_map, inplace=True)

        # Controleer verplichte kolommen (case-insensitive)
        lower_map = {c.lower(): c for c in df_raw.columns}
        missing = [c for c in REQUIRED_COLS if c.lower() not in lower_map]
        if missing:
            flash(f"Ontbrekende kolommen: {', '.join(missing)}", "error")
            return redirect(url_for("griffie.jaarplanning"))

        # Selecteer/hernormeer volgorde
        use_cols = [lower_map[c.lower()] for c in REQUIRED_COLS]
        df = df_raw[use_cols].copy()

        # Parse 'Huidige planning' -> Triaalcode
        huiname = lower_map["huidige planning"]
        tri_codes = []
        ym_cache = []

        for val in df[huiname].tolist():
            res = normalize_to_year_month(val)
            if res is None:
                tri_codes.append("")  # laat leeg als onparseerbaar
                ym_cache.append(None)
            else:
                y, m = res
                tri_codes.append(triaal_label(y, m))
                ym_cache.append((y, m))

        df.insert(df.columns.get_loc(huiname) + 1, "Triaalcode", tri_codes)

        # Bepaal eerstvolgende 3 trialen vanaf nu (Europe/Amsterdam)
        now_ams = datetime.now(ZoneInfo("Europe/Amsterdam"))
        next_labels = compute_next_three_triaal_labels(now_ams)

        # Schrijf naar Excel met kleuren (alleen kolom Triaalcode kleuren)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Jaarplanning")
            ws = writer.book["Jaarplanning"]

            # Zoek kolomindex van Triaalcode
            header_row = 1
            triaal_col_idx = None
            for idx, cell in enumerate(ws[header_row], start=1):
                if str(cell.value).strip().lower() == "triaalcode":
                    triaal_col_idx = idx
                    break

            from openpyxl.styles import PatternFill

            if triaal_col_idx:
                for r in range(2, ws.max_row + 1):
                    val = ws.cell(row=r, column=triaal_col_idx).value
                    if not val:
                        continue
                    fill = PatternFill(start_color=color_for_label(val, next_labels),
                                       end_color=color_for_label(val, next_labels),
                                       fill_type="solid")
                    ws.cell(row=r, column=triaal_col_idx).fill = fill

                # Legenda bovenaan (rij 1 eronder schuiven is complex; we voegen een extra sheet toe)
                legend = writer.book.create_sheet("Legenda")
                legend["A1"] = "Kleurcodering (eerstvolgende trialen vanaf vandaag)"
                legend["A2"] = next_labels[0]; legend["B2"].fill = PatternFill(start_color=COLOR_NEXT_1, end_color=COLOR_NEXT_1, fill_type="solid")
                legend["A3"] = next_labels[1]; legend["B3"].fill = PatternFill(start_color=COLOR_NEXT_2, end_color=COLOR_NEXT_2, fill_type="solid")
                legend["A4"] = next_labels[2]; legend["B4"].fill = PatternFill(start_color=COLOR_NEXT_3, end_color=COLOR_NEXT_3, fill_type="solid")
                legend["A6"] = "Latere trialen"; legend["B6"].fill = PatternFill(start_color=COLOR_LATER, end_color=COLOR_LATER, fill_type="solid")

        output.seek(0)
        # Net bestandsnaam met suffix
        base = filename.rsplit(".", 1)[0]
        download_name = f"{base}_met_triaalcodes.xlsx"

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=download_name,
        )

    except Exception as e:
        # Voor de gebruiker: duidelijke foutmelding
        flash(f"Er ging iets mis bij het verwerken van het bestand: {e}", "error")
        return redirect(url_for("griffie.jaarplanning"))
