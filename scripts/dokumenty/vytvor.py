"""Vyrobí vymyšlené PDF JK pojišťovny z textových souborů v `texty/`.

Formát textu (jednoduchý, podobný Markdownu):

    @kod: VPP-AUTO-2026          metadata na začátku souboru
    @nazev: …                    (kod, nazev, typ, pojisteni, klient, smlouva)
    # Nadpis dokumentu
    ## Článek
    ### Pododdíl
    odstavec (řádky se spojí, odstavce dělí prázdný řádek)
    - odrážka
    1. číslovaný krok
    | a | b |                    tabulka; druhý řádek |---| = první je záhlaví
    > zvýrazněné upozornění
    ===                          nová stránka
    **tučně**

Výstup: `dokumenty/*.pdf` a `dokumenty/seznam.json` (metadata pro pozdější
import do aplikace). Výstup je pokaždé bajtově stejný (`invariant`), takže
v gitu se změní jen dokument, jehož text se změnil.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import PageBreakIfNotEmpty

rl_config.invariant = 1  # bez data vytvoření a náhodného ID → stejné bajty

KOREN = Path(__file__).resolve().parents[2]
TEXTY = Path(__file__).resolve().parent / "texty"
VYSTUP = KOREN / "dokumenty"

PISMO = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
PISMO_TUCNE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
pdfmetrics.registerFont(TTFont("Dejavu", PISMO))
pdfmetrics.registerFont(TTFont("Dejavu-Bold", PISMO_TUCNE))
pdfmetrics.registerFontFamily("Dejavu", normal="Dejavu", bold="Dejavu-Bold")

ZNACKA = colors.HexColor("#1d4a85")
ZNACKA_SVETLA = colors.HexColor("#e2e9f4")
LINKA = colors.HexColor("#c2bbad")
TLUMENA = colors.HexColor("#5b6275")

ZAKLAD = ParagraphStyle("zaklad", fontName="Dejavu", fontSize=9.5, leading=13.5, spaceAfter=5, alignment=TA_LEFT)
STYLY = {
    "h1": ParagraphStyle("h1", parent=ZAKLAD, fontName="Dejavu-Bold", fontSize=17, leading=21, spaceAfter=8, textColor=ZNACKA),
    "h2": ParagraphStyle("h2", parent=ZAKLAD, fontName="Dejavu-Bold", fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=4, textColor=ZNACKA),
    "h3": ParagraphStyle("h3", parent=ZAKLAD, fontName="Dejavu-Bold", fontSize=10, leading=14, spaceBefore=5, spaceAfter=3),
    "p": ZAKLAD,
    "li": ParagraphStyle("li", parent=ZAKLAD, spaceAfter=2),
    "td": ParagraphStyle("td", parent=ZAKLAD, fontSize=9, leading=12, spaceAfter=0),
    "th": ParagraphStyle("th", parent=ZAKLAD, fontName="Dejavu-Bold", fontSize=9, leading=12, spaceAfter=0, textColor=colors.white),
    "box": ParagraphStyle("box", parent=ZAKLAD, spaceAfter=0),
}

POVINNA_METADATA = ("kod", "nazev", "typ", "pojisteni")
TYPY = {"podminky", "informace", "smlouva", "dodatek"}
POJISTENI = {"auto", "domacnost", "cestovni", "obecne"}


def inline(text: str) -> str:
    """Escapuje HTML a převede **tučně** na <b>."""
    text = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def bunky(radek: str) -> list[str]:
    return [b.strip() for b in radek.strip().strip("|").split("|")]


def tabulka(radky: list[str], husta: bool = False) -> Table:
    """Tabulka; `husta` = menší řádkování (smlouvy se tak vejdou na stranu)."""
    ma_zahlavi = len(radky) > 1 and re.fullmatch(r"\|?[\s:\-|]+\|?", radky[1].strip())
    if ma_zahlavi:
        radky = [radky[0]] + radky[2:]
    data = []
    for i, r in enumerate(radky):
        styl = STYLY["th"] if ma_zahlavi and i == 0 else STYLY["td"]
        data.append([Paragraph(inline(b), styl) for b in bunky(r)])
    sloupcu = max(len(r) for r in data)
    for r in data:
        r += [Paragraph("", STYLY["td"])] * (sloupcu - len(r))
    sirka = A4[0] - 40 * mm
    # Dvousloupcová tabulka „údaj | hodnota“ má užší první sloupec.
    sirky = [sirka * 0.38, sirka * 0.62] if sloupcu == 2 else [sirka / sloupcu] * sloupcu
    t = Table(data, colWidths=sirky, repeatRows=1 if ma_zahlavi else 0)
    styl = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINKA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2 if husta else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 if husta else 4),
    ]
    if ma_zahlavi:
        styl.append(("BACKGROUND", (0, 0), (-1, 0), ZNACKA))
    else:
        styl.append(("BACKGROUND", (0, 0), (0, -1), ZNACKA_SVETLA))
    t.setStyle(TableStyle(styl))
    return t


def upozorneni(text: str) -> Table:
    t = Table([[Paragraph(inline(text), STYLY["box"])]], colWidths=[A4[0] - 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ZNACKA_SVETLA),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ZNACKA),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def nacti(soubor: Path) -> tuple[dict[str, str], list]:
    """Přečte textový soubor a vrátí metadata a seznam prvků pro PDF."""
    meta: dict[str, str] = {}
    prvky: list = []
    odstavec: list[str] = []
    odrazky: list[str] = []
    radky_tabulky: list[str] = []

    def uzavri() -> None:
        if odstavec:
            prvky.append(Paragraph(inline(" ".join(odstavec)), STYLY["p"]))
            odstavec.clear()
        if odrazky:
            prvky.append(ListFlowable(
                [ListItem(Paragraph(inline(o), STYLY["li"]), leftIndent=12) for o in odrazky],
                bulletType="bullet", start="•", leftIndent=12, bulletFontName="Dejavu",
            ))
            prvky.append(Spacer(1, 4))
            odrazky.clear()
        if radky_tabulky:
            prvky.append(tabulka(radky_tabulky, meta.get("typ") in {"smlouva", "dodatek"}))
            prvky.append(Spacer(1, 7))
            radky_tabulky.clear()

    for radek in soubor.read_text(encoding="utf-8").splitlines():
        s = radek.strip()
        if not prvky and not odstavec and (m := re.fullmatch(r"@(\w+):\s*(.*)", s)):
            meta[m.group(1)] = m.group(2)
            continue
        if not s:
            uzavri()
        elif s == "===":
            uzavri()
            # Mezera před zalomením by se při plné stránce přelila na novou
            # stránku a zalomení by pak udělalo prázdnou stránku.
            while prvky and isinstance(prvky[-1], Spacer):
                prvky.pop()
            prvky.append(PageBreakIfNotEmpty())
        elif s.startswith("|"):
            if odstavec or odrazky:
                uzavri()
            radky_tabulky.append(s)
        elif s.startswith("### ") or s.startswith("## ") or s.startswith("# "):
            uzavri()
            uroven = len(s.split(" ", 1)[0])
            prvky.append(Paragraph(inline(s[uroven + 1:]), STYLY[f"h{uroven}"]))
        elif s.startswith("- "):
            if odstavec or radky_tabulky:
                uzavri()
            odrazky.append(s[2:])
        elif re.match(r"\d+\. ", s):
            # Číslovaný krok: každý vlastní odstavec, číslo zůstává v textu.
            uzavri()
            prvky.append(Paragraph(inline(s), STYLY["li"]))
        elif s.startswith("> "):
            uzavri()
            prvky.append(upozorneni(s[2:]))
            prvky.append(Spacer(1, 7))
        else:
            if odrazky or radky_tabulky:
                uzavri()
            odstavec.append(s)
    uzavri()

    chybi = [k for k in POVINNA_METADATA if k not in meta]
    if chybi:
        sys.exit(f"{soubor.name}: chybí metadata {chybi}")
    if meta["typ"] not in TYPY or meta["pojisteni"] not in POJISTENI:
        sys.exit(f"{soubor.name}: neznámý typ nebo pojištění")
    if meta["typ"] in {"smlouva", "dodatek"} and not meta.get("klient"):
        sys.exit(f"{soubor.name}: smlouva a dodatek musí mít @klient")

    # Nadpis článku nezůstane osamocený na konci stránky.
    spojene: list = []
    for p in prvky:
        if spojene and isinstance(spojene[-1], Paragraph) and spojene[-1].style.name in {"h2", "h3"}:
            spojene[-1] = KeepTogether([spojene[-1], p])
        else:
            spojene.append(p)
    return meta, spojene


class CislovaneStrany(rl_canvas.Canvas):
    """Plátno, které po vykreslení zná počet stran („Strana 2 z 5“)."""

    kod = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._strany: list[dict] = []

    def showPage(self):  # noqa: N802 (název z reportlabu)
        self._strany.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        celkem = len(self._strany)
        for stav in self._strany:
            self.__dict__.update(stav)
            self._zahlavi_a_zapati(celkem)
            super().showPage()
        super().save()

    def _zahlavi_a_zapati(self, celkem: int) -> None:
        sirka, vyska = A4
        self.setStrokeColor(ZNACKA)
        self.setLineWidth(1.2)
        self.line(20 * mm, vyska - 15 * mm, sirka - 20 * mm, vyska - 15 * mm)
        self.setFillColor(ZNACKA)
        self.setFont("Dejavu-Bold", 10)
        self.drawString(20 * mm, vyska - 13 * mm, "JK pojišťovna, a.s.")
        self.setFont("Dejavu", 8.5)
        self.setFillColor(TLUMENA)
        self.drawRightString(sirka - 20 * mm, vyska - 13 * mm, self.kod)
        self.setStrokeColor(LINKA)
        self.setLineWidth(0.5)
        self.line(20 * mm, 15 * mm, sirka - 20 * mm, 15 * mm)
        self.setFont("Dejavu", 7.5)
        self.drawString(20 * mm, 11 * mm, "Vymyšlený dokument pro ukázku v portfoliu – JK pojišťovna, a.s. neexistuje.")
        self.drawRightString(sirka - 20 * mm, 11 * mm, f"Strana {self._pageNumber} z {celkem}")


def vyrob(soubor: Path) -> dict:
    meta, prvky = nacti(soubor)
    okraj = (19 if meta["typ"] in {"smlouva", "dodatek"} else 22) * mm
    cil = VYSTUP / f"{soubor.stem}.pdf"
    doc = SimpleDocTemplate(
        str(cil), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=okraj, bottomMargin=okraj,
        title=meta["nazev"], author="JK pojišťovna, a.s. (vymyšlená)",
        subject=meta["kod"], creator="asistent-dokumenty / scripts/dokumenty",
    )
    plat = type("Platno", (CislovaneStrany,), {"kod": meta["kod"]})
    doc.build(prvky, canvasmaker=plat)

    # Kontrola: text jde z PDF vytáhnout i s diakritikou (fáze 2 na tom stojí).
    ctenar = PdfReader(str(cil))
    text = "".join(s.extract_text() or "" for s in ctenar.pages)
    if "pojišťovna" not in text:
        sys.exit(f"{cil.name}: z PDF nejde vytáhnout text s diakritikou")
    # Stránka jen se záhlavím a zápatím = chyba sazby (citace by mířila nikam).
    for cislo, strana in enumerate(ctenar.pages, start=1):
        obsah = (strana.extract_text() or "").replace(meta["kod"], "")
        obsah = obsah.replace("JK pojišťovna, a.s. neexistuje.", "").replace("JK pojišťovna, a.s.", "")
        if len(re.sub(r"Strana \d+ z \d+|Vymyšlený dokument pro ukázku v portfoliu –|\s", "", obsah)) < 40:
            sys.exit(f"{cil.name}: strana {cislo} je prázdná")
    return {
        "soubor": cil.name,
        "kod": meta["kod"],
        "nazev": meta["nazev"],
        "typ": meta["typ"],
        "pojisteni": meta["pojisteni"],
        "klient": meta.get("klient"),
        "smlouva": meta.get("smlouva"),
        "stran": len(ctenar.pages),
    }


def main() -> None:
    VYSTUP.mkdir(exist_ok=True)
    seznam = [vyrob(s) for s in sorted(TEXTY.glob("*.txt"))]
    (VYSTUP / "seznam.json").write_text(
        json.dumps(seznam, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for d in seznam:
        print(f"{d['soubor']:<40} {d['stran']} str.  {d['nazev']}")


if __name__ == "__main__":
    main()
