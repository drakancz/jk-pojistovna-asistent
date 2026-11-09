"""Kontrola nahraného souboru podle skutečného obsahu (prvních bajtů),
ne podle přípony ani podle typu, který tvrdí prohlížeč."""

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"


def rozpoznej_typ(obsah: bytes) -> str | None:
    if obsah.startswith(b"%PDF-"):
        return PDF
    if obsah.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if obsah.startswith(b"\xff\xd8\xff"):
        return JPEG
    return None


def bezpecny_nazev(nazev: str | None) -> str:
    """Jen poslední část cesty, bez řídicích znaků, nejvýš 255 znaků."""
    cisty = (nazev or "soubor").replace("\\", "/").rsplit("/", 1)[-1]
    cisty = "".join(z for z in cisty if z.isprintable()).strip()
    return (cisty or "soubor")[:255]
