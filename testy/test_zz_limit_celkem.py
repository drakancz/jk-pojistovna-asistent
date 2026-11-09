"""Celkový denní limit asistenta (100 na serveru, v testech 40 přes
AI_LIMIT_CELKEM). Soubor běží jako POSLEDNÍ (název test_zz…): po něm
už asistent v testovacím běhu neodpoví nikomu.

Před dalším během doma zastav testovací server (`docker compose
--profile test stop web-test db-test`) — databáze v paměti se vymaže
a limit začne znovu."""

from conftest import csrf, napodobenina, odesli_formular

CELKOVY = "Asistent má pro dnešek vyčerpaný celkový limit otázek."


def test_celkovy_limit(prihlas):
    odmitnuto = None
    for ucet in ("admin", "likvidace"):
        page = prihlas(ucet)
        for _ in range(25):
            odpoved = odesli_formular(page, "/asistent", data={"csrf": csrf(page), "otazka": "Co je totální škoda?"})
            if odpoved.status != 200:
                odmitnuto = odpoved
                break
        if odmitnuto is not None and CELKOVY in odmitnuto.text():
            break
    assert odmitnuto is not None and odmitnuto.status == 429
    assert CELKOVY in odmitnuto.text()

    # Celkový limit platí pro každého a k AI už nic neodejde.
    page = prihlas("admin")
    pred = napodobenina("/_posledni")["pocet"]
    odpoved = odesli_formular(page, "/asistent", data={"csrf": csrf(page), "otazka": "Ještě jedna?"})
    assert odpoved.status == 429
    assert napodobenina("/_posledni")["pocet"] == pred
