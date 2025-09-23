from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import Iterable, Dict, Any, Optional
from docx.shared import Pt
from docxtpl import DocxTemplate
from slugify import slugify
from flask import current_app
from docx.enum.style import WD_STYLE_TYPE


# ---- helpers ---------------------------------------------------------------
PREFERRED_BULLET_STYLE = "MotieBullet"  # maak deze in je DOCX (zie uitleg onderaan)

_BULLET_STYLE_CANDIDATES = [
    PREFERRED_BULLET_STYLE,
    "List Paragraph",                # EN
    "Bulleted List",                 # EN (soms)
    "List Bullet",                   # EN (soms)
    "Lijst met opsommingstekens",    # NL
    "Opsomming",                     # NL (soms)
    "Liste à puces",                 # FR
    "Aufzählungszeichen",            # DE
    "Párrafo de lista",              # ES
]

def _find_available_style(doc: DocxTemplate) -> str | None:
    styles = doc.docx.styles
    names = {s.name for s in styles if s.type == WD_STYLE_TYPE.PARAGRAPH}
    for name in _BULLET_STYLE_CANDIDATES:
        if name in names:
            return name
    return None

def build_bullet_list(doc: DocxTemplate, items):
    sd = doc.new_subdoc()
    style_name = _find_available_style(doc)

    for txt in (items or []):
        t = str(txt).strip()
        if not t:
            continue

        if style_name:
            p = sd.add_paragraph(t, style=style_name)
        else:
            # Fallback: visueel identiek aan bullets (geen echte Word-lijst, maar strak en compact)
            p = sd.add_paragraph()
            p.add_run("• ")
            p.add_run(t)

        fmt = p.paragraph_format
        fmt.space_before = Pt(0)
        fmt.space_after = Pt(0)
        fmt.line_spacing = 1  # Enkel

    return sd
def _ensure_iter(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # splits op newline of ; als je tekstveld hebt
        parts = [p.strip() for p in value.split("\n") if p.strip()]
        return parts
    if isinstance(value, Iterable):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]

def _filename_for_motie(title: str) -> str:
    # 'Motie <titel>.docx' met veilige bestandsnaam
    safe = slugify(title or "", lowercase=False, separator=" ")
    safe = safe.strip()
    if not safe:
        safe = "Zonder titel"
    return f"Motie {safe}.docx"

def _template_path() -> Path:
    # Standaardlocatie voor je vaste template
    base = Path(current_app.root_path).parent  # project root /app/..
    # Als je app structuur anders is, pas dit pad aan:
    # hier gaan we uit van app/templates_word/motie_template.docx
    p = base / "app" / "templates_word" / "motie.docx"
    return p

# ---- public API ------------------------------------------------------------

def render_motie_to_docx_bytes(motie, *, vergadering: Optional[str] = None,
                               datum: Optional[str] = None) -> tuple[bytes, str]:
    """
    Rendert de motie in het vaste Word-sjabloon en geeft (bytes, filename) terug.
    - motie: je SQLAlchemy-object of dataclass met o.a. .titel, .constaterende, .overwegende, .opdrachten, .toelichting
    - vergadering/datum: optioneel extra metavelden voor in het sjabloon
    """
    tpl_path = _template_path()
    if not tpl_path.exists():
        raise FileNotFoundError(
            f"Word-sjabloon niet gevonden op {tpl_path}. "
            f"Zet je vaste format in app/templates_word/motie_template.docx of update _template_path()."
        )
    doc = DocxTemplate(str(tpl_path))

    # Bouw context vanuit je motie-model
    # Pas veldnamen aan aan jouw model (hier aannames op basis van je eerdere beschrijving)
    titel = getattr(motie, "titel", "") or ""
    opdracht_formulering = getattr(motie, "opdracht_formulering", "") or ""
    gemeenteraad_datum = getattr(motie, "gemeenteraad_datum", "") or ""
    agendapunt = getattr(motie, "agendapunt", "") or ""
   
    # Deze drie kunnen in jouw app lijsten zijn (arrays) of strings; we normaliseren naar lijst
    constaterende_dat = build_bullet_list(doc, _ensure_iter(getattr(motie, "constaterende_dat", [])))
    overwegende_dat   = build_bullet_list(doc, _ensure_iter(getattr(motie, "overwegende_dat", [])))
    draagt_college_op    = build_bullet_list(doc, _ensure_iter(getattr(motie, "draagt_college_op", [])))  # aka 'draagt het college op'

    # Indieners (optioneel): pas aan aan jouw relatiemodel
    # Voorbeeld: motie.indieners -> lijst van User/Fractie-relaties met .naam of .fractie.naam
    # indieners_namen = []
    # if hasattr(motie, "indieners") and motie.indieners:
    #    for ind in motie.indieners:
    #        # probeer 'naam' of 'display_name'
    #        naam = getattr(ind, "naam", None) or getattr(ind, "display_name", None) or str(ind)
    #        indieners_namen.append(naam)
    #indieners_inline = ", ".join(indieners_namen) if indieners_namen else ""

    context: Dict[str, Any] = {
        "titel": titel,
        "gemeenteraad_datum": gemeenteraad_datum,
        "agendapunt": agendapunt,
        "opdracht_formulering": opdracht_formulering,
        "constaterende_dat": constaterende_dat,
        "overwegende_dat": overwegende_dat,
        "draagt_college_op": draagt_college_op,
    }

    # Renderen
    doc.render(context)

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)

    return bio.read(), _filename_for_motie(titel)