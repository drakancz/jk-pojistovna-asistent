"""Evaluace asistenta (krok 5A): měřená čísla místo dojmu.

Dvě části:

1. **Vyhledávání** (bez AI, zdarma): najde aplikace pro otázku správnou
   stránku mezi prvními pěti úryvky? A nedostane klientka mezi úryvky
   cizí smlouvu? Běží kdykoli, i bez klíče k Anthropicu.
2. **Odpovědi** (s klíčem): stejné úryvky a pokyny jako skutečný asistent
   (`asistent.parametry()`), poslané hromadně přes Message Batches API
   (o 50 % levnější, výsledek do hodiny). Hodnotí se, jestli odpověď
   obsahuje správné údaje, cituje správný dokument a stránku a jestli
   na otázku mimo dokumenty řekne „nevím“. Volba `primo` posílá otázky
   jednu po druhé (bez slevy, hned).

Evaluace nejde přes denní limit asistenta a nic nezapisuje do databáze.
Spouští se příkazem `python -m app.prikazy evaluace` (viz `docs/evaluace.md`).
"""

import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import asistent, hledani
from app.evaluace_sada import CIZI_PETRE, SADA
from app.modely import Role, Uzivatel

PETRA = "petra.mala@jk-pojistovna.test"
NA_PRVNICH = 5  # vyhledávání: správná stránka mezi prvními pěti
# Ceník Claude Haiku 5.5 (USD za milion tokenů, ověřeno 3. 11. 2026);
# hromadné zpracování má slevu 50 %.
CENA_VSTUP, CENA_VYSTUP = 0.10, 0.50


@dataclass
class Vysledek:
    id: str
    druh: str
    kdo: str
    otazka: str
    # Vyhledávání
    poradi: int | None = None  # pořadí správného úryvku (1–5), None = nenašlo
    cizi_v_hledani: list[str] = field(default_factory=list)
    # Odpověď (jen s klíčem)
    odpoved: str | None = None
    nevim: bool | None = None
    citace: list[str] = field(default_factory=list)  # „dokument, strana N“
    udaje_ok: bool | None = None
    citace_ok: bool | None = None
    cizi_poslano: list[str] = field(default_factory=list)
    spravne: bool | None = None
    chyba: str | None = None


def _normalizuj(text: str) -> str:
    """Malá písmena, jednotné mezery (i pevné a úzké), bez rozdílu „–“ a „-“."""
    text = unicodedata.normalize("NFKC", text).replace(" ", " ").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def obsahuje(text: str, udaj: str | tuple[str, ...]) -> bool:
    """Údaj jako n-tice = stačí kterákoli varianta („6 týdnů“ / „šest týdnů“)."""
    varianty = udaj if isinstance(udaj, tuple) else (udaj,)
    return any(_normalizuj(v) in _normalizuj(text) for v in varianty)


def _uzivatele(db: Session) -> dict[str, Uzivatel]:
    petra = db.scalar(select(Uzivatel).where(Uzivatel.email == PETRA))
    if petra is None:
        raise SystemExit("Chybí ukázková klientka Petra Malá — nejdřív `python -m app.prikazy ukazkove-dokumenty`.")
    # Likvidace vidí všechny dokumenty; k hledání stačí role, účet netřeba.
    return {"likvidace": Uzivatel(id=0, email="", jmeno="evaluace", role=Role.LIKVIDACE, otisk_hesla=""), "petra": petra}


def _trefa(nalez: hledani.Nalez | asistent.Zdroj, zdroje: list) -> bool:
    return any(nalez.dokument == dokument and nalez.strana == strana for dokument, strana in zdroje)


def _hledej(
    db: Session, uzivatele: dict[str, Uzivatel], otazka: dict, pocet: int, slova: dict[str, str | None] | None = None
) -> list[hledani.Nalez]:
    kdo = uzivatele[otazka["kdo"]]
    return hledani.hledej(
        db,
        otazka["otazka"],
        hledani.viditelne_dokumenty(kdo),
        pocet=pocet,
        klient=kdo.role == Role.KLIENT,
        doplnek=(slova or {}).get(otazka["id"]),
    )


def prevod_otazek(sada: list[dict] = SADA) -> tuple[dict[str, str | None], int, int]:
    """Otázky převedené do slov dokumentů, stejně jako u skutečného
    asistenta (`asistent.hledaci_slova`). Jen s klíčem; bez něj se měří
    hledání podle samotné otázky (zdarma)."""
    slova: dict[str, str | None] = {}
    vstup = vystup = 0
    for o in sada:
        slova[o["id"]], v, w = asistent.hledaci_slova(o["otazka"])
        vstup, vystup = vstup + v, vystup + w
    return slova, vstup, vystup


def vyhledavani(db: Session, sada: list[dict] = SADA, slova: dict[str, str | None] | None = None) -> list[Vysledek]:
    uzivatele = _uzivatele(db)
    vysledky = []
    for o in sada:
        v = Vysledek(id=o["id"], druh=o["druh"], kdo=o["kdo"], otazka=o["otazka"])
        nalezy = _hledej(db, uzivatele, o, NA_PRVNICH, slova)
        if o["druh"] == "odpoved":
            v.poradi = next((i for i, n in enumerate(nalezy, 1) if _trefa(n, o["zdroje"])), None)
        if o["kdo"] == "petra":
            v.cizi_v_hledani = sorted({n.dokument for n in nalezy if n.dokument in CIZI_PETRE})
        vysledky.append(v)
    return vysledky


def _ohodnot(v: Vysledek, o: dict, odpoved: asistent.Odpoved) -> None:
    v.odpoved = " ".join(c.text for c in odpoved.casti).strip()
    v.nevim = odpoved.nevim or _normalizuj(v.odpoved).startswith("nevím")
    v.citace = [f"{z.dokument}, strana {z.strana}" for z in odpoved.zdroje]
    # Cizí jsou Benešovy smlouvy jen pro klientku; likvidace je vidět smí.
    if v.kdo == "petra":
        v.cizi_poslano = sorted({n.dokument for n in odpoved.poslane if n.dokument in CIZI_PETRE})
    if o["druh"] == "odpoved":
        v.udaje_ok = not v.nevim and all(obsahuje(v.odpoved, u) for u in o["udaje"])
        v.citace_ok = any(_trefa(z, o["zdroje"]) for z in odpoved.zdroje)
        v.spravne = v.udaje_ok and v.citace_ok
    elif o["druh"] == "nevim":
        v.spravne = v.nevim
    else:  # opravneni: cizí smlouva nesmí k AI odejít ani se objevit v odpovědi
        v.spravne = not v.cizi_poslano and not any(obsahuje(v.odpoved, z) for z in o["zakazane"])


def odpovedi(db: Session, vysledky: list[Vysledek], sada: list[dict] = SADA, primo: bool = False,
             cekat_max_s: int = 3600, slova: dict[str, str | None] | None = None,
             spotreba_prevodu: tuple[int, int] = (0, 0)) -> dict:
    """Doplní k výsledkům odpovědi asistenta a vrátí spotřebu tokenů."""
    if not asistent.je_zapnuty():
        raise SystemExit("Odpovědi potřebují klíč k Anthropicu (ANTHROPIC_API_KEY). Vyhledávání běží i bez něj.")
    uzivatele = _uzivatele(db)
    podle_id = {v.id: v for v in vysledky}
    otazky = {o["id"]: o for o in sada}
    pozadavky: dict[str, tuple[dict, list[hledani.Nalez]]] = {}
    for o in sada:
        nalezy = _hledej(db, uzivatele, o, asistent.POCET_URYVKU, slova)
        if not nalezy:  # asistent by Claude vůbec nevolal a řekl „nevím“
            _ohodnot(podle_id[o["id"]], o, asistent.Odpoved(casti=[asistent.Cast(text=asistent.NEVIM)],
                                                             zdroje=[], poslane=[], nevim=True))
            continue
        pozadavky[o["id"]] = (asistent.parametry(o["otazka"], nalezy), nalezy)

    klient = asistent._klient()
    spotreba = {"vstup": 0, "vystup": 0, "hromadne": not primo}

    def zpracuj(id_: str, zprava) -> None:
        spotreba["vstup"] += zprava.usage.input_tokens
        spotreba["vystup"] += zprava.usage.output_tokens
        _ohodnot(podle_id[id_], otazky[id_], asistent.sloz(zprava, pozadavky[id_][1]))

    if primo:
        for id_, (parametry, _) in pozadavky.items():
            zpracuj(id_, klient.messages.create(**parametry))
    else:
        davka = klient.messages.batches.create(
            requests=[{"custom_id": id_, "params": parametry} for id_, (parametry, _) in pozadavky.items()]
        )
        konec = time.monotonic() + cekat_max_s
        while davka.processing_status != "ended":
            if time.monotonic() > konec:
                raise SystemExit(f"Dávka {davka.id} se nestihla zpracovat; výsledky jdou stáhnout později.")
            time.sleep(20)
            davka = klient.messages.batches.retrieve(davka.id)
        for radek in klient.messages.batches.results(davka.id):
            if radek.result.type == "succeeded":
                zpracuj(radek.custom_id, radek.result.message)
            else:
                podle_id[radek.custom_id].chyba = radek.result.type
                podle_id[radek.custom_id].spravne = False
    sleva = 0.5 if not primo else 1.0
    # Převod otázek jde jednotlivě (bez slevy dávky), proto se počítá zvlášť.
    pv, pw = spotreba_prevodu
    spotreba["cena_usd"] = round(
        ((spotreba["vstup"] * CENA_VSTUP + spotreba["vystup"] * CENA_VYSTUP) * sleva
         + pv * CENA_VSTUP + pw * CENA_VYSTUP) / 1_000_000, 4
    )
    spotreba["vstup"] += pv
    spotreba["vystup"] += pw
    return spotreba


def _podil(cast: int, celek: int) -> str:
    return f"{cast} z {celek} ({round(100 * cast / celek)} %)" if celek else "—"


def souhrn(vysledky: list[Vysledek], spotreba: dict | None = None) -> dict:
    s_odpovedi = [v for v in vysledky if v.druh == "odpoved"]
    petra = [v for v in vysledky if v.kdo == "petra"]
    trefy = [v for v in s_odpovedi if v.poradi]
    vysledek = {
        "datum": datetime.now(asistent.PRAHA).strftime("%Y-%m-%d %H:%M"),
        "otazek": len(vysledky),
        "hledani_trefa": len(trefy),
        "hledani_celkem": len(s_odpovedi),
        "hledani_prvni": sum(1 for v in trefy if v.poradi == 1),
        # Střední převrácené pořadí: 1 = správný úryvek vždy první.
        "hledani_mrr": round(sum(1 / v.poradi for v in trefy) / len(s_odpovedi), 3) if s_odpovedi else 0,
        "cizi_v_hledani": sum(1 for v in petra if v.cizi_v_hledani),
        "dotazu_klientky": len(petra),
    }
    if spotreba is not None:
        def pocet(druh, pole="spravne"):
            return sum(1 for v in vysledky if v.druh == druh and getattr(v, pole))
        vysledek |= {
            "odpovedi": True,
            "spravne": sum(1 for v in vysledky if v.spravne),
            "udaje_ok": pocet("odpoved", "udaje_ok"),
            "citace_ok": pocet("odpoved", "citace_ok"),
            "odpoved_celkem": len(s_odpovedi),
            "nevim_ok": pocet("nevim"),
            "nevim_celkem": sum(1 for v in vysledky if v.druh == "nevim"),
            "opravneni_ok": pocet("opravneni"),
            "opravneni_celkem": sum(1 for v in vysledky if v.druh == "opravneni"),
            "cizi_poslano": sum(1 for v in vysledky if v.cizi_poslano),
            "spotreba": spotreba,
        }
    return vysledek


def zprava_md(s: dict, vysledky: list[Vysledek]) -> str:
    """Zpráva pro člověka (Markdown). Bez textu odpovědí — jen čísla a značky."""
    r = [
        f"# Evaluace asistenta – {s['datum']}",
        "",
        f"Sada: {s['otazek']} otázek (`app/evaluace_sada.py`).",
        "",
        "## Vyhledávání (bez AI)",
        "",
        f"- Správná stránka mezi prvními {NA_PRVNICH}: **{_podil(s['hledani_trefa'], s['hledani_celkem'])}**",
        f"- Správná stránka hned první: {_podil(s['hledani_prvni'], s['hledani_celkem'])}",
        f"- Střední převrácené pořadí (MRR): {s['hledani_mrr']}",
        f"- Cizí smlouva ve výsledcích klientky: **{s['cizi_v_hledani']} z {s['dotazu_klientky']} dotazů** (musí být 0)",
    ]
    if s.get("odpovedi"):
        sp = s["spotreba"]
        r += [
            "",
            "## Odpovědi asistenta",
            "",
            f"- Celkem správně: **{_podil(s['spravne'], s['otazek'])}**",
            f"- Správné údaje: {_podil(s['udaje_ok'], s['odpoved_celkem'])}",
            f"- Citace správného dokumentu a stránky: {_podil(s['citace_ok'], s['odpoved_celkem'])}",
            f"- „Nevím“ u otázek mimo dokumenty: {_podil(s['nevim_ok'], s['nevim_celkem'])}",
            f"- Oprávnění (cizí smlouva neodešla ani se neobjevila): {_podil(s['opravneni_ok'], s['opravneni_celkem'])}",
            f"- Spotřeba: {sp['vstup']} vstupních a {sp['vystup']} výstupních tokenů, "
            f"asi {sp['cena_usd']} $ ({'hromadně, −50 %' if sp['hromadne'] else 'jednotlivě'})",
        ]
    r += ["", "## Otázky", "", "| Otázka | Druh | Hledání | Odpověď |", "|---|---|---|---|"]
    for v in vysledky:
        hledani_ = (f"{v.poradi}." if v.poradi else "✗") if v.druh == "odpoved" else "—"
        if v.cizi_v_hledani:
            hledani_ = "✗ cizí smlouva"
        odpoved = "—" if v.spravne is None else ("✓" if v.spravne else "✗")
        if v.spravne is False and v.druh == "odpoved":
            odpoved += " " + ", ".join(
                t for t, ok in (("údaje", v.udaje_ok), ("citace", v.citace_ok)) if not ok
            )
        r.append(f"| {v.otazka} | {v.druh} | {hledani_} | {odpoved} |")
    return "\n".join(r) + "\n"


def spust(db: Session, s_odpovedmi: bool, primo: bool, vystup: Path | None, zprava: Path | None) -> dict:
    if s_odpovedmi:
        if not asistent.je_zapnuty():
            raise SystemExit("Odpovědi potřebují klíč k Anthropicu (ANTHROPIC_API_KEY). Vyhledávání běží i bez něj.")
        slova, pv, pw = prevod_otazek()
        vysledky = vyhledavani(db, slova=slova)
        spotreba = odpovedi(db, vysledky, primo=primo, slova=slova, spotreba_prevodu=(pv, pw))
    else:
        vysledky = vyhledavani(db)
        spotreba = None
    s = souhrn(vysledky, spotreba)
    if vystup:
        vystup.parent.mkdir(parents=True, exist_ok=True)
        vystup.write_text(json.dumps({"souhrn": s, "otazky": [asdict(v) for v in vysledky]},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    if zprava:
        zprava.parent.mkdir(parents=True, exist_ok=True)
        zprava.write_text(zprava_md(s, vysledky), encoding="utf-8")
    return s
