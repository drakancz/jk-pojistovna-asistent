"""Vyrobí vymyšlená „naskenovaná“ hlášení škody JK pojišťovny (krok 4A).

Zdroj: `hlaseni.json` vedle tohoto souboru. Každá položka se nakreslí jako
formulář „Hlášení pojistné události“ vyplněný „rukou“ (písmo Comic Neue,
modře, s drobnými nepravidelnostmi) a pak se „naskenuje“ podle `kvalita`:

    cisty      barevný sken, PNG
    pootoceny  šedý sken, mírně pootočený, PDF bez textové vrstvy
    fotka      fotka mobilem: šikmo, stín, okraje stolu, JPEG
    spatny     nízký kontrast, šum, rozmazání, PNG
    kopie      kopie kopie: tmavý zrnitý tisk, skvrna od kávy, PDF bez textu

Výstup: `dokumenty/11-…` až `15-…` a `dokumenty/hlaseni.json` (metadata pro
import a správné údaje pro měření vytěžení). Náhoda má pevné semínko podle
názvu souboru, takže výstup je pokaždé bajtově stejný.
"""

from __future__ import annotations

import io
import json
import random
import sys
import tempfile
from datetime import date
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfReader
from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

rl_config.invariant = 1  # bez data vytvoření a náhodného ID → stejné bajty

KOREN = Path(__file__).resolve().parents[2]
ZDROJ = Path(__file__).resolve().parent / "hlaseni.json"
VYSTUP = KOREN / "dokumenty"

# A4 při 150 dpi: dost na čtení, a obrázek zůstane pod limity Claude API.
SIRKA, VYSKA = 1240, 1754
OKRAJ = 80
OBSAH = SIRKA - 2 * OKRAJ

DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_TUCNE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
RUKOPIS = "/usr/share/fonts/opentype/comic-neue/ComicNeue-Regular.otf"

TISK = ImageFont.truetype(DEJAVU, 19)
TISK_TUCNE = ImageFont.truetype(DEJAVU_TUCNE, 20)
POPISEK = ImageFont.truetype(DEJAVU, 15)
NADPIS = ImageFont.truetype(DEJAVU_TUCNE, 34)
DROBNE = ImageFont.truetype(DEJAVU, 14)
RUKA = ImageFont.truetype(RUKOPIS, 27)

CERNA = (30, 30, 34)
SEDA = (95, 99, 110)
LINKA = (120, 124, 135)
PODKLAD = (228, 232, 240)
ZNACKA = (29, 74, 133)
INKOUST = (28, 48, 140)

POJISTENI = {
    "auto": "Havarijní pojištění vozidla",
    "domacnost": "Pojištění domácnosti",
    "cestovni": "Cestovní pojištění",
}
ZAPATI = "Vymyšlený dokument pro ukázku v portfoliu – JK pojišťovna, a.s. neexistuje."
MAX_BAJTU = 3_500_000  # obrázek pro OCR (Claude bere nejvýš 5 MB)


# --- Formátování hodnot tak, jak by je napsal člověk -------------------------

def datum(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def castka(cislo: int | None, mena: str = "CZK") -> str:
    if cislo is None:
        return ""
    return f"{cislo:,}".replace(",", " ") + (" Kč" if mena == "CZK" else f" {mena}")


def hodnoty(polozka: dict) -> dict[str, str]:
    """Co je na formuláři napsané v každém poli (s přepisy z `zapis`)."""
    u = polozka["udaje"]
    v = {k: ("" if h is None else str(h)) for k, h in u.items() if not isinstance(h, list)}
    v["datum_udalosti"] = datum(u["datum_udalosti"])
    v["datum_podpisu"] = datum(u["datum_podpisu"])
    v["odhad_skody"] = castka(u["odhad_skody"], u["mena"])
    v.update(polozka.get("zapis", {}))
    return v


# --- Kreslení ----------------------------------------------------------------

class Strana:
    """Jedna stránka formuláře; `pole` si pamatuje, kde je které pole."""

    def __init__(self, rng: random.Random, cislo: int, celkem: int):
        self.img = Image.new("RGB", (SIRKA, VYSKA), "white")
        self.d = ImageDraw.Draw(self.img)
        self.rng = rng
        self.y = OKRAJ
        self.pole: dict[str, tuple[int, int, int, int]] = {}
        self._zahlavi_a_zapati(cislo, celkem)

    def _zahlavi_a_zapati(self, cislo: int, celkem: int) -> None:
        d = self.d
        d.text((OKRAJ, self.y), "JK pojišťovna, a.s.", font=TISK_TUCNE, fill=ZNACKA)
        d.text((SIRKA - OKRAJ, self.y + 2), "Formulář HS-01 (2026)", font=POPISEK, fill=SEDA, anchor="ra")
        self.y += 32
        d.line((OKRAJ, self.y, SIRKA - OKRAJ, self.y), fill=ZNACKA, width=3)
        self.y += 22
        d.line((OKRAJ, VYSKA - 70, SIRKA - OKRAJ, VYSKA - 70), fill=LINKA, width=1)
        d.text((OKRAJ, VYSKA - 60), ZAPATI, font=DROBNE, fill=SEDA)
        d.text((SIRKA - OKRAJ, VYSKA - 60), f"Strana {cislo} z {celkem}", font=DROBNE, fill=SEDA, anchor="ra")

    def nadpis(self, text: str, podtitul: str = "") -> None:
        self.d.text((OKRAJ, self.y), text, font=NADPIS, fill=CERNA)
        self.y += 48
        if podtitul:
            self.d.text((OKRAJ, self.y), podtitul, font=POPISEK, fill=SEDA)
            self.y += 30
        self.y += 6

    def oddil(self, text: str) -> None:
        self.y += 8
        self.d.rectangle((OKRAJ, self.y, SIRKA - OKRAJ, self.y + 32), fill=PODKLAD)
        self.d.text((OKRAJ + 10, self.y + 5), text, font=TISK_TUCNE, fill=CERNA)
        self.y += 32

    def ruka(self, x: float, y: float, text: str) -> float:
        """Text „rukou“: každé písmeno trochu jinak posazené, řádek mírně šikmo."""
        sklon = self.rng.uniform(-0.012, 0.012)
        zacatek = x
        for znak in text:
            dy = sklon * (x - zacatek) + self.rng.uniform(-1.3, 1.3)
            self.d.text((x, y + dy), znak, font=RUKA, fill=INKOUST)
            x += RUKA.getlength(znak) * self.rng.uniform(0.97, 1.06)
        return x

    def radek(self, pole: list[tuple[str, str, float]], v: dict[str, str], vyska: int = 62) -> None:
        """Řada políček: (popisek, klíč hodnoty, podíl šířky)."""
        x = OKRAJ
        for popisek, klic, podil in pole:
            w = round(OBSAH * podil)
            self.d.rectangle((x, self.y, x + w, self.y + vyska), outline=LINKA, width=1)
            self.d.text((x + 8, self.y + 5), popisek, font=POPISEK, fill=SEDA)
            self.pole[klic] = (x, self.y, w, vyska)
            if v.get(klic):
                self.ruka(x + 14, self.y + vyska - 38, v[klic])
            x += w
        self.y += vyska

    def popis(self, popisek: str, klic: str, text: str) -> None:
        """Víceřádkové pole; text se zalomí podle šířky."""
        radky, aktualni = [], ""
        for slovo in text.split():
            zkus = f"{aktualni} {slovo}".strip()
            if RUKA.getlength(zkus) * 1.04 > OBSAH - 40:
                radky.append(aktualni)
                aktualni = slovo
            else:
                aktualni = zkus
        radky.append(aktualni)
        vyska = 34 + 38 * max(len(radky), 3)
        self.d.rectangle((OKRAJ, self.y, SIRKA - OKRAJ, self.y + vyska), outline=LINKA, width=1)
        self.d.text((OKRAJ + 8, self.y + 5), popisek, font=POPISEK, fill=SEDA)
        self.pole[klic] = (OKRAJ, self.y, OBSAH, vyska)
        for i, r in enumerate(radky):
            self.ruka(OKRAJ + 14, self.y + 28 + 38 * i, r)
        self.y += vyska

    def zaskrtavatka(self, otazka: str, moznosti: list[tuple[str, bool]]) -> None:
        x = OKRAJ + 10
        if otazka:
            self.d.text((x, self.y + 14), otazka, font=TISK, fill=CERNA)
            x += TISK.getlength(otazka) + 30
        for text, zaskrtnuto in moznosti:
            self.d.rectangle((x, self.y + 12, x + 26, self.y + 38), outline=CERNA, width=2)
            if zaskrtnuto:
                self._krizek(x + 13, self.y + 25)
            self.d.text((x + 36, self.y + 14), text, font=TISK, fill=CERNA)
            x += 36 + TISK.getlength(text) + 50
        self.y += 50

    def _krizek(self, cx: float, cy: float) -> None:
        r = self.rng.uniform
        self.d.line((cx - 13 + r(-2, 2), cy - 14 + r(-2, 2), cx + 14 + r(-2, 2), cy + 12 + r(-2, 2)), fill=INKOUST, width=4)
        self.d.line((cx + 13 + r(-2, 2), cy - 15 + r(-2, 2), cx - 12 + r(-2, 2), cy + 13 + r(-2, 2)), fill=INKOUST, width=4)

    def text(self, text: str) -> None:
        self.d.text((OKRAJ + 4, self.y + 8), text, font=POPISEK, fill=CERNA)
        self.y += 30

    def podpis(self, klic: str) -> None:
        """Klikyhák do pole podpisu."""
        x, y, w, h = self.pole[klic]
        body, px = [], x + 40
        while px < x + w - 60:
            body.append((px, y + h - 30 + self.rng.uniform(-14, 10)))
            px += self.rng.uniform(9, 22)
        self.d.line(body, fill=INKOUST, width=3, joint="curve")
        self.d.line((x + 30, y + h - 14, x + w * 0.7, y + h - 18), fill=INKOUST, width=2)

    def preskrtni(self, klic: str, stara: str, nova: str) -> None:
        """Hodnota přeškrtnutá a vedle napsaná opravená."""
        x, y, w, h = self.pole[klic]
        konec = self.ruka(x + 14, y + h - 38, stara)
        for posun in (-3, 3):
            self.d.line((x + 8, y + h - 22 + posun, konec + 6, y + h - 26 + posun), fill=INKOUST, width=3)
        self.ruka(konec + 24, y + h - 40, nova)


def formular(polozka: dict, rng: random.Random, celkem: int) -> Strana:
    v = hodnoty(polozka)
    u = polozka["udaje"]
    s = Strana(rng, 1, celkem)
    s.nadpis(
        "HLÁŠENÍ POJISTNÉ UDÁLOSTI",
        "Vyplňte čitelně. Pošlete na skody@jk-pojistovna.example nebo na adresu Na Ukázce 10, 110 00 Praha 1.",
    )
    s.oddil("1. Pojistník")
    s.radek([("Jméno a příjmení pojistníka", "pojistnik", 0.62), ("Číslo pojistné smlouvy", "cislo_smlouvy", 0.38)], v)
    s.radek([("Adresa", "adresa", 1.0)], v)
    s.radek([("Telefon", "telefon", 0.38), ("E-mail", "email", 0.62)], v)
    s.oddil("2. Druh pojištění")
    s.zaskrtavatka("", [(n, k == u["pojisteni"]) for k, n in POJISTENI.items()])
    s.oddil("3. Pojistná událost")
    s.radek([("Datum události", "datum_udalosti", 0.5), ("Čas", "cas_udalosti", 0.5)], v)
    s.radek([("Místo události", "misto", 1.0)], v)
    s.radek([("Co se stalo", "druh_udalosti", 1.0)], v)
    s.popis("Popis události a rozsah škody", "popis", v["popis"])
    s.oddil("4. Osoby a vozidlo (vyplňte, co se vás týká)")
    s.radek([("Řidič vozidla", "ridic", 0.62), ("Registrační značka", "registracni_znacka", 0.38)], v)
    s.radek([("Poškozená nebo ošetřená osoba (jméno, datum narození)", "poskozena_osoba", 1.0)], v)
    s.radek([("Svědek nebo jiný účastník (jméno, telefon)", "svedek", 1.0)], v)
    s.oddil("5. Škoda a policie")
    if "odhad_skody_preskrtnuto" in v:
        s.radek([("Odhad výše škody", "odhad_skody_x", 0.5), ("Číslo jednací policie", "cislo_jednaci", 0.5)], v)
        s.preskrtni("odhad_skody_x", v["odhad_skody_preskrtnuto"], v["odhad_skody"])
    else:
        s.radek([("Odhad výše škody", "odhad_skody", 0.5), ("Číslo jednací policie", "cislo_jednaci", 0.5)], v)
    s.zaskrtavatka("Šetřila událost policie?", [("ano", u["policie"]), ("ne", not u["policie"])])
    s.oddil("6. Prohlášení a podpis")
    s.text("Prohlašuji, že jsem všechny údaje uvedl(a) pravdivě a úplně. Beru na vědomí, že nepravdivé údaje")
    s.text("mohou vést ke snížení nebo odmítnutí plnění." + (" Seznam poškozených věcí je v příloze." if u["polozky"] else ""))
    s.radek([("V (místo)", "misto_podpisu", 0.34), ("Dne", "datum_podpisu", 0.26), ("Podpis pojistníka", "podpis", 0.40)], v, vyska=84)
    s.podpis("podpis")
    if s.y > VYSKA - 80:
        sys.exit(f"{polozka['soubor']}: formulář se nevejde na stránku ({s.y} px)")
    return s


def priloha(polozka: dict, rng: random.Random) -> Strana:
    """Druhá strana: seznam poškozených věcí."""
    u = polozka["udaje"]
    s = Strana(rng, 2, 2)
    s.nadpis("PŘÍLOHA – SEZNAM POŠKOZENÝCH VĚCÍ", f"K hlášení pojistné události ke smlouvě č. {u['cislo_smlouvy']}")
    s.oddil("Poškozené nebo zničené věci")
    sloupce = [("Věc", 0.56), ("Rok pořízení", 0.18), ("Pořizovací cena", 0.26)]
    x = OKRAJ
    for nazev, podil in sloupce:
        w = round(OBSAH * podil)
        s.d.rectangle((x, s.y, x + w, s.y + 36), outline=LINKA, fill=PODKLAD)
        s.d.text((x + 8, s.y + 8), nazev, font=POPISEK, fill=CERNA)
        x += w
    s.y += 36
    radky = [(p["vec"], str(p["rok_porizeni"]), castka(p["cena"])) for p in u["polozky"]]
    radky += [("", "", "")] * 3 + [("Celkem", "", castka(sum(p["cena"] for p in u["polozky"])))]
    for hodnoty_radku in radky:
        x = OKRAJ
        for (_, podil), h in zip(sloupce, hodnoty_radku, strict=True):
            w = round(OBSAH * podil)
            s.d.rectangle((x, s.y, x + w, s.y + 56), outline=LINKA)
            if h:
                s.ruka(x + 14, s.y + 14, h)
            x += w
        s.y += 56
    s.y += 30
    s.radek([("V (místo)", "misto_podpisu", 0.34), ("Dne", "datum_podpisu", 0.26), ("Podpis pojistníka", "podpis", 0.40)], hodnoty(polozka), vyska=84)
    s.podpis("podpis")
    return s


# --- „Skenování“ ---------------------------------------------------------------

def sum_(velikost: tuple[int, int], rng: random.Random) -> Image.Image:
    """Šum s pevným semínkem (Image.effect_noise semínko nemá)."""
    return Image.frombytes("L", velikost, rng.randbytes(velikost[0] * velikost[1]))


def rozsah(img: Image.Image, tmava: int, svetla: int) -> Image.Image:
    """Stlačí jas do rozsahu tmava–svetla (šedý papír, vybledlý toner)."""
    return img.point(lambda h: tmava + h * (svetla - tmava) // 255)


def skvrna(img: Image.Image, stred: tuple[int, int], r: int) -> Image.Image:
    """Skvrna od hrnku kávy: světlá výplň, tmavší okraj, rozmazaná."""
    vrstva = Image.new("L", img.size, 255)
    d = ImageDraw.Draw(vrstva)
    cx, cy = stred
    d.ellipse((cx - r, cy - r * 0.92, cx + r, cy + r * 0.92), fill=232)
    d.arc((cx - r, cy - r * 0.92, cx + r, cy + r * 0.92), 200, 520, fill=165, width=7)
    d.ellipse((cx - r * 0.6, cy + r * 0.5, cx - r * 0.3, cy + r * 0.75), fill=215)  # kapka
    vrstva = vrstva.filter(ImageFilter.GaussianBlur(3))
    return ImageChops.multiply(img, vrstva if img.mode == "L" else Image.merge("RGB", [vrstva] * 3))


def naskenuj(strana: Strana, kvalita: str, rng: random.Random) -> Image.Image:
    img = strana.img
    if kvalita == "cisty":
        img = ImageChops.multiply(img, Image.new("RGB", img.size, (251, 249, 243)))
        return img.rotate(0.3, Image.Resampling.BICUBIC, fillcolor=(251, 249, 243))
    if kvalita == "pootoceny":
        img = rozsah(img.convert("L"), 30, 236)
        img = img.rotate(rng.choice([1.4, -1.1]), Image.Resampling.BICUBIC, fillcolor=236)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        return Image.blend(img, sum_(img.size, rng), 0.06)
    if kvalita == "spatny":
        img = rozsah(img.convert("L"), 95, 214)
        img = img.rotate(-0.7, Image.Resampling.BICUBIC, fillcolor=214)
        img = img.filter(ImageFilter.GaussianBlur(1.1))
        return Image.blend(img, sum_(img.size, rng), 0.14)
    if kvalita == "kopie":
        x, y, w, h = strana.pole["popis"]
        img = skvrna(img.convert("L"), (x + round(w * 0.62), y + h // 2), 95)
        img = img.filter(ImageFilter.GaussianBlur(1.0))
        img = img.point(lambda h: max(0, min(255, (h - 70) * 3 // 2)))  # přepálený kontrast
        d = ImageDraw.Draw(img)
        for _ in range(4000):  # zrnka toneru
            px, py = rng.randrange(img.width), rng.randrange(img.height)
            d.point((px, py), fill=rng.randrange(0, 90))
        okraj = Image.linear_gradient("L").rotate(90).resize((40, img.height))
        img.paste(ImageChops.multiply(img.crop((0, 0, 40, img.height)), okraj), (0, 0))
        return img.rotate(0.5, Image.Resampling.BICUBIC, fillcolor=200)
    if kvalita == "fotka":
        stul = Image.new("RGB", (img.width + 260, img.height + 260), (118, 92, 66))
        stul = Image.blend(stul, Image.merge("RGB", [sum_(stul.size, rng)] * 3), 0.08)
        stul.paste(img, (130, 130))
        # Šikmý pohled: list se zužuje nahoru a je trochu pootočený.
        roh = (60, 20, 70, stul.height - 40, stul.width - 110, stul.height - 10, stul.width - 20, 70)
        img = stul.transform((img.width, img.height), Image.Transform.QUAD, roh, Image.Resampling.BICUBIC)
        # Světlo shora (dole tmavší) a měkký stín ruky s telefonem vpravo dole.
        stin = Image.linear_gradient("L").point(lambda h: 255 - h * 70 // 255).resize(img.size)
        ruka = Image.new("L", img.size, 255)
        ImageDraw.Draw(ruka).ellipse((img.width * 0.55, img.height * 0.62, img.width * 1.3, img.height * 1.25), fill=120)
        stin = ImageChops.multiply(stin, ruka.filter(ImageFilter.GaussianBlur(140)))
        img = ImageChops.multiply(img, Image.merge("RGB", [stin] * 3))
        return img.filter(ImageFilter.GaussianBlur(0.8))
    sys.exit(f"Neznámá kvalita skenu: {kvalita}")


# --- Uložení -------------------------------------------------------------------

def jako_jpeg(img: Image.Image, kvalita: int) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=kvalita, optimize=True)
    return b.getvalue()


def uloz(polozka: dict, stranky: list[Image.Image]) -> Path:
    cil = VYSTUP / polozka["soubor"]
    if cil.suffix == ".png":
        img = stranky[0]
        img.save(cil, "PNG", optimize=True)
    elif cil.suffix == ".jpg":
        cil.write_bytes(jako_jpeg(stranky[0], 72))
    elif cil.suffix == ".pdf":
        # PDF jen z obrázků — žádná textová vrstva, musí se číst přes OCR.
        c = rl_canvas.Canvas(str(cil), pagesize=A4, invariant=1)
        c.setTitle(polozka["nazev"])
        c.setAuthor("JK pojišťovna, a.s. (vymyšlená)")
        c.setCreator("asistent-dokumenty / scripts/dokumenty/skeny.py")
        # Pevná cesta: reportlab z názvu souboru odvozuje jméno obrázku v PDF.
        for i, img in enumerate(stranky):
            soubor = Path(tempfile.gettempdir()) / f"sken-strana-{i + 1}.jpg"
            soubor.write_bytes(jako_jpeg(img, 75))
            c.drawImage(str(soubor), 0, 0, width=A4[0], height=A4[1])
            c.showPage()
        c.save()
    else:
        sys.exit(f"{cil.name}: neznámá přípona")
    return cil


def zkontroluj(cil: Path, stran: int) -> None:
    velikost = cil.stat().st_size
    if cil.suffix == ".pdf":
        ctenar = PdfReader(str(cil))
        if len(ctenar.pages) != stran:
            sys.exit(f"{cil.name}: má {len(ctenar.pages)} stran místo {stran}")
        for cislo, strana in enumerate(ctenar.pages, start=1):
            if (strana.extract_text() or "").strip():
                sys.exit(f"{cil.name}: strana {cislo} má textovou vrstvu (sken ji mít nesmí)")
        if velikost / stran > MAX_BAJTU:
            sys.exit(f"{cil.name}: příliš velké stránky ({velikost} B)")
    elif velikost > MAX_BAJTU:
        sys.exit(f"{cil.name}: příliš velký obrázek ({velikost} B)")


def vyrob(polozka: dict) -> dict:
    u = polozka["udaje"]
    if u["pojisteni"] not in POJISTENI:
        sys.exit(f"{polozka['soubor']}: neznámé pojištění")
    rng = random.Random(polozka["soubor"])
    celkem = 2 if u["polozky"] else 1
    if celkem == 2 and not polozka["soubor"].endswith(".pdf"):
        sys.exit(f"{polozka['soubor']}: dvoustránkové hlášení musí být PDF")
    stranky = [formular(polozka, rng, celkem)] + ([priloha(polozka, rng)] if celkem == 2 else [])
    cil = uloz(polozka, [naskenuj(s, polozka["kvalita"], rng) for s in stranky])
    zkontroluj(cil, celkem)
    return {
        "soubor": cil.name,
        "kod": f"HS-{u['cislo_smlouvy']}",
        "nazev": polozka["nazev"],
        "typ": "hlaseni",
        "pojisteni": u["pojisteni"],
        "klient": u["pojistnik"],
        "smlouva": u["cislo_smlouvy"],
        "stran": celkem,
        "kvalita": polozka["kvalita"],
        "potize": polozka["potize"],
        "spravne_udaje": u,
        # Jak klient pole doslova napsal, když se liší (vytěžení opsané
        # doslova se pak při měření počítá taky jako správné).
        "zapis": polozka.get("zapis", {}),
    }


def main() -> None:
    zdroj = json.loads(ZDROJ.read_text(encoding="utf-8"))
    seznam = [vyrob(p) for p in zdroj["hlaseni"]]
    (VYSTUP / "hlaseni.json").write_text(json.dumps(seznam, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for d in seznam:
        velikost = (VYSTUP / d["soubor"]).stat().st_size // 1000
        print(f"{d['soubor']:<34} {d['stran']} str. {velikost:>5} kB  {d['kvalita']:<10} {d['nazev']}")


if __name__ == "__main__":
    main()
