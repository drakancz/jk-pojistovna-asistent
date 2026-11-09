"""Evaluace asistenta (krok 5A). Testovací server ji pustí při startu nad
čistými dokumenty (`scripts/test-server.sh`) a výsledek uloží do
/stav/evaluace.json. Odpovědi tam dává napodobenina Anthropicu, takže se
neměří chytrost modelu, ale to, že měření počítá správně, jde přes
hromadnou dávku a nic citlivého neodchází. Vyhledávání je skutečné."""

import json
from pathlib import Path

import pytest

from conftest import napodobenina

MINIMUM_HLEDANI = 23  # z 27 otázek s odpovědí; 8. 11. 2026 našlo 23, 9. 11. po úpravě hledání 25


@pytest.fixture(scope="module")
def evaluace() -> dict:
    return json.loads(Path("/stav/evaluace.json").read_text(encoding="utf-8"))


def test_vyhledavani_najde_spravnou_stranku(evaluace):
    s = evaluace["souhrn"]
    assert s["hledani_celkem"] == 27
    assert s["hledani_trefa"] >= MINIMUM_HLEDANI, s


def test_klientka_cizi_smlouvu_nenajde_ani_neposle(evaluace):
    s = evaluace["souhrn"]
    assert s["dotazu_klientky"] == 6
    assert s["cizi_v_hledani"] == 0
    assert s["cizi_poslano"] == 0
    assert s["opravneni_ok"] == s["opravneni_celkem"] == 3


def test_hodnoceni_odpovedi_pocita_spravne(evaluace):
    """Napodobenina cituje vždy první poslaný úryvek a „nevím“ říká jen
    u kurzu eura. Hodnocení proto musí sedět přesně s vyhledáváním."""
    otazky = {o["id"]: o for o in evaluace["otazky"]}
    assert otazky["nevim-kurz"]["spravne"] is True
    assert otazky["nevim-zivotni"]["spravne"] is False  # napodobenina odpověděla, „nevím“ chybí
    for o in evaluace["otazky"]:
        if o["druh"] != "odpoved":
            continue
        # Citace je správná právě tehdy, když hledání našlo správnou stránku jako první.
        assert o["citace_ok"] == (o["poradi"] == 1), o["id"]
        assert o["citace"], o["id"]
    # Otázka bez povinných údajů se hodnotí jen citací.
    assert otazky["auto-klice"]["udaje_ok"] is True
    # Text napodobeniny číslo neobsahuje, údaje tedy nesedí.
    assert otazky["auto-kradez-policie"]["udaje_ok"] is False
    assert evaluace["souhrn"]["spravne"] == sum(1 for o in evaluace["otazky"] if o["spravne"])


def test_odpovedi_sly_hromadnou_davkou_bez_osobnich_udaju(evaluace):
    davka = napodobenina("/_posledni")["davka"]
    assert davka is not None, "evaluace neposlala hromadnou dávku"
    assert davka["pozadavku"] == evaluace["souhrn"]["otazek"]
    assert davka["modely"] == ["claude-haiku-5-5"]
    assert davka["citace"] is True
    # Smlouvy obsahují vymyšlený e-mail a telefon: k AI nesmí odejít (krok 5B).
    assert davka["osobni_udaje"] is False
    assert evaluace["souhrn"]["spotreba"]["hromadne"] is True
