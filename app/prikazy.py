"""Příkazy pro správu účtů (spouští se v kontejneru, ne v prohlížeči).

Veřejná registrace neexistuje. Hesla se nevymýšlejí v kódu ani v rozhovoru:
každé je náhodné a zapíše se jen do souboru mimo repozitář.

    python -m app.prikazy vyvojove-ucty            # tři účty pro vývoj
    python -m app.prikazy zaloz-ucet --email … --jmeno … --role ADMIN
    python -m app.prikazy testove-ucty --soubor /stav/ucty.json   # jen testy
    python -m app.prikazy ukazkove-dokumenty      # 10 PDF a 5 skenů hlášení škody + 2 klienti
    python -m app.prikazy obnov-ukazku             # jen s UKAZKA=1: účty, dokumenty, noční obnova
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select

from app import cteni
from app.bezpecnost import nove_heslo, otisk_hesla, sjednot_email
from app.db import nove_sezeni
from app.modely import Audit, Dokument, DruhDokumentu, Pojisteni, Role, Uzivatel
from app.soubory import JPEG, PDF, PNG, rozpoznej_typ

SOUBOR_VYVOJ = Path("data/ucty-vyvoj.txt")
SOUBOR_UKAZKA = Path("data/ucty-ukazka.txt")
DOKUMENTY = Path("dokumenty")

# Vymyšlení klienti z dokumentů (krok 1C). Petra Malá bude ukázkový účet.
UKAZKOVI_KLIENTI = {
    "Petra Malá": "petra.mala@jk-pojistovna.test",
    "Tomáš Beneš": "tomas.benes@jk-pojistovna.test",
}
DRUH_ZE_SEZNAMU = {
    "podminky": DruhDokumentu.PODMINKY,
    "informace": DruhDokumentu.PODMINKY,  # vidí všichni jako podmínky
    "smlouva": DruhDokumentu.SMLOUVA,
    "dodatek": DruhDokumentu.SMLOUVA,  # dodatek patří ke smlouvě a jejímu klientovi
    "hlaseni": DruhDokumentu.HLASENI,  # sken (krok 4A), patří klientovi
}
POJISTENI_ZE_SEZNAMU = {
    "auto": Pojisteni.AUTO,
    "domacnost": Pojisteni.DOMACNOST,
    "cestovni": Pojisteni.CESTOVNI,
    "obecne": Pojisteni.OBECNE,
}


def ukazkove_dokumenty(zapsat_hesla: bool = True) -> None:
    """Nahraje PDF z `dokumenty/` (podle seznam.json) a skeny hlášení škody
    (podle hlaseni.json) a hned je přečte. Skeny jdou přes OCR — bez klíče
    k Anthropicu zůstanou ve stavu „čeká na OCR“ a nic neodchází. Co už
    v systému je (stejný obsah), přeskočí; heslo existujícího klienta
    nemění."""
    seznam = [
        polozka
        for nazev in ("seznam.json", "hlaseni.json")
        for polozka in json.loads((DOKUMENTY / nazev).read_text(encoding="utf-8"))
    ]
    nova_hesla: list[str] = []
    k_precteni: list[int] = []
    with nove_sezeni() as db:
        admin = db.scalar(select(Uzivatel).where(Uzivatel.role == Role.ADMIN).order_by(Uzivatel.id))
        if admin is None:
            sys.exit("Nejdřív založte administrátora (vyvojove-ucty nebo zaloz-ucet).")
        klienti: dict[str, Uzivatel] = {}
        for jmeno, email in UKAZKOVI_KLIENTI.items():
            klient = db.scalar(select(Uzivatel).where(Uzivatel.email == email))
            if klient is None:
                heslo = nove_heslo()
                klient = Uzivatel(email=email, jmeno=jmeno, role=Role.KLIENT, otisk_hesla=otisk_hesla(heslo))
                db.add(klient)
                db.flush()
                db.add(Audit(uzivatel_id=None, akce="ucet_zalozen", podrobnosti={"ucet_id": klient.id}))
                nova_hesla.append(f"{email}\t{heslo}\tKLIENT")
            klienti[jmeno] = klient

        for polozka in seznam:
            obsah = (DOKUMENTY / polozka["soubor"]).read_bytes()
            typ = rozpoznej_typ(obsah)
            povolene = {PDF, PNG, JPEG} if polozka["typ"] == "hlaseni" else {PDF}
            if typ not in povolene:
                sys.exit(f"{polozka['soubor']}: nepovolený typ souboru.")
            otisk = hashlib.sha256(obsah).hexdigest()
            if db.scalar(select(Dokument.id).where(Dokument.sha256 == otisk)):
                continue
            klient = klienti[polozka["klient"]] if polozka.get("klient") else None
            dokument = Dokument(
                nazev=polozka["nazev"],
                nazev_souboru=polozka["soubor"],
                druh=DRUH_ZE_SEZNAMU[polozka["typ"]],
                pojisteni=POJISTENI_ZE_SEZNAMU[polozka["pojisteni"]],
                klient_id=klient.id if klient else None,
                typ_obsahu=typ,
                velikost=len(obsah),
                sha256=otisk,
                obsah=obsah,
                nahral_id=admin.id,
            )
            db.add(dokument)
            db.flush()
            db.add(
                Audit(
                    uzivatel_id=None,
                    akce="dokument_nahran",
                    podrobnosti={"dokument_id": dokument.id, "nazev": dokument.nazev, "velikost": dokument.velikost},
                )
            )
            k_precteni.append(dokument.id)
        db.commit()

    for dokument_id in k_precteni:
        cteni.precti(dokument_id)
    # Živá ukázka (obnov-ukazku) hesla nezapisuje: na serveru nemá kam a heslo
    # druhého klienta nepotřebuje (ukázkové účty mají známé heslo).
    if nova_hesla and zapsat_hesla:
        SOUBOR_UKAZKA.parent.mkdir(parents=True, exist_ok=True)
        with SOUBOR_UKAZKA.open("a", encoding="utf-8") as f:
            f.write("\n".join(nova_hesla) + "\n")
        os.chmod(SOUBOR_UKAZKA, 0o600)
        print(f"Klienti založeni, hesla jsou v souboru {SOUBOR_UKAZKA} (mimo repozitář).")
    print(f"Nahráno a přečteno dokumentů: {len(k_precteni)} (ostatní už v systému byly).")

VYVOJOVE_UCTY = [
    ("admin@jk-pojistovna.test", "Alena Správcová", Role.ADMIN),
    ("likvidace@jk-pojistovna.test", "Libor Likvidátor", Role.LIKVIDACE),
    ("klient@jk-pojistovna.test", "Karel Klient", Role.KLIENT),
]

TESTOVE_UCTY = {
    "admin": ("admin@test.invalid", "Test Administrátor", Role.ADMIN),
    "likvidace": ("likvidace@test.invalid", "Test Likvidace", Role.LIKVIDACE),
    "klient": ("klient@test.invalid", "Test Klient Jedna", Role.KLIENT),
    "klient2": ("klient2@test.invalid", "Test Klient Dva", Role.KLIENT),
    # Jen pro test denního limitu asistenta (vyčerpá svých 20 otázek).
    "limit": ("limit@test.invalid", "Test Limit", Role.LIKVIDACE),
    # Klienti z dokumentů JK pojišťovny (krok 3B): testy založí účty dřív než
    # `ukazkove-dokumenty`, který pak jejich smlouvy přiřadí k nim — heslo
    # z tohohle běhu tak zůstane platné.
    "petra": (UKAZKOVI_KLIENTI["Petra Malá"], "Petra Malá", Role.KLIENT),
    "tomas": (UKAZKOVI_KLIENTI["Tomáš Beneš"], "Tomáš Beneš", Role.KLIENT),
}


def zaloz_nebo_nastav(email: str, jmeno: str, role: Role) -> str:
    """Založí účet, nebo existujícímu nastaví nové náhodné heslo. Vrátí heslo."""
    heslo = nove_heslo()
    with nove_sezeni() as db:
        uzivatel = db.scalar(select(Uzivatel).where(Uzivatel.email == sjednot_email(email)))
        if uzivatel is None:
            uzivatel = Uzivatel(email=sjednot_email(email), jmeno=jmeno, role=role, otisk_hesla="")
            db.add(uzivatel)
            akce = "ucet_zalozen"
        else:
            akce = "heslo_nastaveno"
        uzivatel.otisk_hesla = otisk_hesla(heslo)
        db.flush()
        # Do historie nikdy heslo ani otisk.
        db.add(Audit(uzivatel_id=None, akce=akce, podrobnosti={"ucet_id": uzivatel.id}))
        db.commit()
    return heslo


def _zapis_soukrome(soubor: Path, text: str) -> None:
    soubor.parent.mkdir(parents=True, exist_ok=True)
    soubor.write_text(text, encoding="utf-8")
    os.chmod(soubor, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.prikazy")
    pod = parser.add_subparsers(dest="prikaz", required=True)

    pod.add_parser("vyvojove-ucty", help="tři účty pro vývoj, hesla do data/ucty-vyvoj.txt")

    jeden = pod.add_parser("zaloz-ucet", help="založí účet nebo mu nastaví nové heslo")
    jeden.add_argument("--email", required=True)
    jeden.add_argument("--jmeno", required=True)
    jeden.add_argument("--role", required=True, choices=[r.value for r in Role])
    jeden.add_argument("--soubor", default=str(SOUBOR_VYVOJ.with_name("ucet-novy.txt")))

    test = pod.add_parser("testove-ucty", help="jen pro testy: účty do JSON souboru")
    test.add_argument("--soubor", required=True)

    pod.add_parser("ukazkove-dokumenty", help="10 PDF a 5 skenů hlášení JK pojišťovny, klienti Petra Malá a Tomáš Beneš")
    pod.add_parser("obnov-ukazku", help="jen s UKAZKA=1: ukázkové účty, dokumenty (poprvé) a obnova dne")

    ev = pod.add_parser("evaluace", help="měření kvality asistenta (krok 5A): vyhledávání, s --odpovedi i odpovědi AI")
    ev.add_argument("--odpovedi", action="store_true", help="i odpovědi asistenta (potřebuje klíč, stojí haléře)")
    ev.add_argument("--primo", action="store_true", help="otázky jednu po druhé místo hromadné dávky (bez slevy)")
    ev.add_argument("--vystup", default="data/evaluace.json", help="podrobné výsledky (JSON, mimo repozitář)")
    ev.add_argument("--zprava", default="", help="zpráva pro člověka (Markdown), např. docs/evaluace-vysledky.md")

    argumenty = parser.parse_args()

    if argumenty.prikaz == "ukazkove-dokumenty":
        ukazkove_dokumenty()
        return

    if argumenty.prikaz == "obnov-ukazku":
        from app import ukazka

        if not ukazka.je_ukazka():
            sys.exit("Obnova ukázky běží jen s UKAZKA=1.")
        obnoveno = ukazka.obnov()
        # Poprvé na prázdné databázi: nahrát a přečíst ukázkové dokumenty
        # (OCR skenů jen tentokrát, pak už se jen obnovují opravy).
        if not ukazka.ma_dokumenty():
            ukazkove_dokumenty(zapsat_hesla=False)
        print("Ukázka obnovena." if obnoveno else "Ukázka už dnes obnovená je.")
        return

    if argumenty.prikaz == "evaluace":
        from app import evaluace  # načte model pro hledání, jen když je potřeba

        with nove_sezeni() as db:
            s = evaluace.spust(db, argumenty.odpovedi, argumenty.primo, Path(argumenty.vystup),
                               Path(argumenty.zprava) if argumenty.zprava else None)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return

    if argumenty.prikaz == "vyvojove-ucty":
        radky = [
            f"{email}\t{zaloz_nebo_nastav(email, jmeno, role)}\t{role.value}"
            for email, jmeno, role in VYVOJOVE_UCTY
        ]
        _zapis_soukrome(SOUBOR_VYVOJ, "\n".join(radky) + "\n")
        print(f"Účty jsou založené, hesla jsou v souboru {SOUBOR_VYVOJ} (mimo repozitář).")
    elif argumenty.prikaz == "zaloz-ucet":
        heslo = zaloz_nebo_nastav(argumenty.email, argumenty.jmeno, Role(argumenty.role))
        _zapis_soukrome(Path(argumenty.soubor), f"{sjednot_email(argumenty.email)}\t{heslo}\n")
        print(f"Hotovo, heslo je v souboru {argumenty.soubor}.")
    elif argumenty.prikaz == "testove-ucty":
        if "_test" not in os.environ.get("DATABASE_URL", ""):
            sys.exit("Testové účty jen v testovací databázi (název s _test).")
        ucty = {
            klic: {"email": email, "jmeno": jmeno, "heslo": zaloz_nebo_nastav(email, jmeno, role)}
            for klic, (email, jmeno, role) in TESTOVE_UCTY.items()
        }
        _zapis_soukrome(Path(argumenty.soubor), json.dumps(ucty, ensure_ascii=False))
        print("Testové účty jsou připravené.")


if __name__ == "__main__":
    main()
