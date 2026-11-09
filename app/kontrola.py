"""Kontrola vytěžených údajů člověkem (krok 4C).

Pracovník likvidace vidí návrh od AI ve formuláři, opraví ho a potvrdí.
Opravené údaje jdou do `vytezeni.udaje` (návrh AI zůstává kvůli měření
přesnosti), každá změna do historie (`audit`) ve stejné transakci.

Pravidla (Jakub, 4. 11. 2026):
- opravuje, potvrzuje a vrací ke kontrole **jen likvidace**; administrátor
  údaje vidí jen pro čtení,
- potvrzené údaje jdou **vrátit ke kontrole** (zapíše se do historie),
- „Vytěžit znovu“ jde jen dokud na údaje nikdo nesáhl — práce člověka se
  nikdy nepřepíše,
- administrátor u ukázkových hlášení vidí přesnost AI i po kontrole.

Souběh: formulář nese číslo verze. Uloží se jen tehdy, když se verze
od načtení nezměnila (podmíněný zápis), jinak se nic nepřepíše.
"""

import re
from collections.abc import Mapping
from datetime import date

from pydantic import ValidationError

from app.vytezeni import MAX_DELKA_TEXTU, POLE, UdajeHlaseni, zobraz

MAX_POLOZEK = 30
PRAZDNYCH_RADKU = 3
MAX_CASTKA = 100_000_000
NEJSTARSI_ROK = 1900

# Jak se údaj ve formuláři vyplňuje (vše ostatní je textové pole).
VYBERY = {
    "pojisteni": [("auto", "Havarijní pojištění vozidla"), ("domacnost", "Pojištění domácnosti"),
                  ("cestovni", "Cestovní pojištění")],
    "mena": [("CZK", "Kč"), ("EUR", "EUR"), ("USD", "USD"), ("GBP", "GBP"), ("CHF", "CHF")],
    "policie": [("ano", "ano"), ("ne", "ne")],
}
DATA = {"datum_udalosti", "datum_podpisu"}
CISLA = {"odhad_skody"}
DLOUHE = {"popis", "adresa"}
CAS = re.compile(r"^(\d{1,2})[:.](\d{2})$")


def druh_pole(klic: str) -> str:
    if klic in VYBERY:
        return "vyber"
    if klic in DATA:
        return "datum"
    if klic in CISLA:
        return "cislo"
    if klic == "polozky":
        return "polozky"
    return "dlouhy" if klic in DLOUHE else "text"


# --- Hodnoty pro formulář --------------------------------------------------------

def do_formulare(udaje: dict) -> dict:
    """Uložené údaje → texty do políček formuláře."""
    hodnoty: dict = {}
    for klic, _, _ in POLE:
        h = udaje.get(klic)
        if klic == "polozky":
            hodnoty[klic] = [
                {"vec": p.get("vec") or "", "rok": "" if p.get("rok_porizeni") is None else str(p["rok_porizeni"]),
                 "cena": "" if p.get("cena") is None else str(p["cena"])}
                for p in (h or [])
            ]
        elif klic == "policie":
            hodnoty[klic] = "" if h is None else ("ano" if h else "ne")
        else:
            hodnoty[klic] = "" if h is None else str(h)
    return hodnoty


def radky_polozek(hodnoty: dict) -> list[dict]:
    """Řádky seznamu věcí ve formuláři: vyplněné + pár prázdných na doplnění."""
    radky = list(hodnoty.get("polozky") or [])
    volnych = min(PRAZDNYCH_RADKU, MAX_POLOZEK - len(radky))
    return radky + [{"vec": "", "rok": "", "cena": ""} for _ in range(max(volnych, 0))]


# --- Čtení odeslaného formuláře ----------------------------------------------------

def _cele_cislo(text: str) -> int | None:
    text = text.replace(" ", "").replace(" ", "")
    return int(text) if text.isdigit() else None


def precti(formular: Mapping[str, str]) -> tuple[dict, dict, dict[str, str]]:
    """Odeslaný formulář → (údaje ve tvaru UdajeHlaseni, texty z políček
    pro znovuzobrazení, chyby klíč → hláška). Při chybě jsou údaje prázdné."""
    hodnoty: dict = {}
    udaje: dict = {}
    chyby: dict[str, str] = {}
    dnes = date.today()

    for klic, _, _ in POLE:
        if klic == "polozky":
            continue
        text = str(formular.get(klic, "")).strip()
        hodnoty[klic] = text
        if not text:
            udaje[klic] = None
            continue
        if len(text) > MAX_DELKA_TEXTU:
            chyby[klic] = f"Nejvýš {MAX_DELKA_TEXTU} znaků."
            continue
        druh = druh_pole(klic)
        if druh == "vyber":
            povolene = {k for k, _ in VYBERY[klic]}
            if text not in povolene:
                chyby[klic] = "Vyberte jednu z nabízených možností."
            else:
                udaje[klic] = (text == "ano") if klic == "policie" else text
        elif druh == "datum":
            try:
                d = date.fromisoformat(text)
            except ValueError:
                chyby[klic] = "Zadejte platné datum."
                continue
            if not NEJSTARSI_ROK <= d.year <= dnes.year + 1:
                chyby[klic] = "Datum je mimo rozumný rozsah."
            else:
                udaje[klic] = d.isoformat()
        elif druh == "cislo":
            cislo = _cele_cislo(text)
            if cislo is None or cislo > MAX_CASTKA:
                chyby[klic] = "Zadejte celé číslo bez haléřů, např. 18 500."
            else:
                udaje[klic] = cislo
        elif klic == "cas_udalosti":
            shoda = CAS.match(text)
            if not shoda or int(shoda[1]) > 23 or int(shoda[2]) > 59:
                chyby[klic] = "Zadejte čas jako 14:30."
            else:
                udaje[klic] = f"{int(shoda[1])}:{shoda[2]}"
        else:
            udaje[klic] = text

    polozky = []
    radky = []
    for i in range(MAX_POLOZEK):
        vec = str(formular.get(f"polozka-{i}-vec", "")).strip()
        rok = str(formular.get(f"polozka-{i}-rok", "")).strip()
        cena = str(formular.get(f"polozka-{i}-cena", "")).strip()
        if not (vec or rok or cena):
            continue
        radky.append({"vec": vec, "rok": rok, "cena": cena})
        n = len(radky)
        if not vec:
            chyby.setdefault("polozky", f"Řádek {n}: vyplňte, o jakou věc jde.")
        elif len(vec) > MAX_DELKA_TEXTU:
            chyby.setdefault("polozky", f"Řádek {n}: nejvýš {MAX_DELKA_TEXTU} znaků.")
        rok_cislo = _cele_cislo(rok) if rok else None
        if rok and (rok_cislo is None or not NEJSTARSI_ROK <= rok_cislo <= dnes.year):
            chyby.setdefault("polozky", f"Řádek {n}: rok pořízení zadejte jako čtyřmístné číslo, např. 2021.")
        cena_cislo = _cele_cislo(cena) if cena else None
        if cena and (cena_cislo is None or cena_cislo > MAX_CASTKA):
            chyby.setdefault("polozky", f"Řádek {n}: cenu zadejte jako celé číslo, např. 12 000.")
        polozky.append({"vec": vec, "rok_porizeni": rok_cislo, "cena": cena_cislo})
    hodnoty["polozky"] = radky
    udaje["polozky"] = polozky

    if chyby:
        return {}, hodnoty, chyby
    try:
        # Stejná kontrola tvaru jako u odpovědi AI (krok 4B).
        overene = UdajeHlaseni.model_validate(udaje).model_dump(mode="json")
    except ValidationError:
        return {}, hodnoty, {"_": "Údaje se nepodařilo ověřit. Zkontrolujte je a zkuste to znovu."}
    return overene, hodnoty, {}


# --- Rozdíly ---------------------------------------------------------------------

def rozdily(puvodni: dict, nove: dict) -> dict[str, dict[str, str]]:
    """Které údaje se změnily — pro historii, jak je vidí člověk."""
    zmeny = {}
    for klic, _, _ in POLE:
        pred, po = puvodni.get(klic), nove.get(klic)
        if klic == "odhad_skody":
            # Částka s jinou měnou je jiná částka.
            pred_text, po_text = zobraz(klic, pred, puvodni), zobraz(klic, po, nove)
        else:
            pred_text, po_text = zobraz(klic, pred), zobraz(klic, po)
        if pred_text != po_text:
            zmeny[klic] = {"puvodne": pred_text, "nove": po_text}
    return zmeny


def opraveno_oproti_ai(navrh: dict, udaje: dict | None) -> dict[str, str]:
    """Klíč → co navrhla AI, u údajů, které člověk změnil."""
    if not udaje:
        return {}
    return {klic: z["puvodne"] for klic, z in rozdily(navrh, udaje).items()}
