"""Tabulky v databázi. Schéma se mění jen migrací (Alembic), nikdy ručně."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, deferred, mapped_column, relationship


class Zaklad(DeclarativeBase):
    pass


class Role(enum.StrEnum):
    KLIENT = "KLIENT"
    LIKVIDACE = "LIKVIDACE"
    ADMIN = "ADMIN"


NAZVY_ROLI = {
    Role.KLIENT: "Klient",
    Role.LIKVIDACE: "Pracovník likvidace",
    Role.ADMIN: "Administrátor",
}


class DruhDokumentu(enum.StrEnum):
    PODMINKY = "PODMINKY"
    SMLOUVA = "SMLOUVA"
    HLASENI = "HLASENI"


NAZVY_DRUHU = {
    DruhDokumentu.PODMINKY: "Pojistné podmínky",
    DruhDokumentu.SMLOUVA: "Smlouva",
    DruhDokumentu.HLASENI: "Hlášení škody",
}


class Pojisteni(enum.StrEnum):
    AUTO = "AUTO"
    DOMACNOST = "DOMACNOST"
    CESTOVNI = "CESTOVNI"
    # Dokument pro všechna pojištění (jak hlásit škodu, osobní údaje).
    OBECNE = "OBECNE"


NAZVY_POJISTENI = {
    Pojisteni.AUTO: "Havarijní pojištění auta",
    Pojisteni.DOMACNOST: "Pojištění domácnosti",
    Pojisteni.CESTOVNI: "Cestovní pojištění",
    Pojisteni.OBECNE: "Všechna pojištění",
}


class StavCteni(enum.StrEnum):
    """Jak daleko je čtení dokumentu (text z PDF, OCR, úryvky)."""

    CEKA = "CEKA"
    CTE_SE = "CTE_SE"
    PRECTENO = "PRECTENO"
    CEKA_NA_OCR = "CEKA_NA_OCR"
    CHYBA = "CHYBA"


NAZVY_STAVU_CTENI = {
    StavCteni.CEKA: "Čeká na přečtení",
    StavCteni.CTE_SE: "Čte se…",
    StavCteni.PRECTENO: "Přečteno",
    StavCteni.CEKA_NA_OCR: "Čeká na OCR",
    StavCteni.CHYBA: "Chyba čtení",
}


def _cas() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Uzivatel(Zaklad):
    __tablename__ = "uzivatele"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Vždy malými písmeny (sjednocuje app.bezpecnost.sjednot_email).
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    jmeno: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), nullable=False)
    # Jen otisk Argon2, nikdy heslo.
    otisk_hesla: Mapped[str] = mapped_column(String(255), nullable=False)
    vytvoreno: Mapped[datetime] = _cas()


class Sezeni(Zaklad):
    """Přihlášení. V cookie je náhodný token, v databázi jen jeho otisk."""

    __tablename__ = "sezeni"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    otisk_tokenu: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    uzivatel_id: Mapped[int] = mapped_column(
        ForeignKey("uzivatele.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Token proti podvrženému odeslání formuláře (CSRF), vázaný na sezení.
    csrf: Mapped[str] = mapped_column(String(64), nullable=False)
    vytvoreno: Mapped[datetime] = _cas()
    plati_do: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    uzivatel: Mapped[Uzivatel] = relationship(lazy="joined")


class NeuspesnePrihlaseni(Zaklad):
    """Neúspěšné pokusy o přihlášení podle adresy — omezení počtu pokusů."""

    __tablename__ = "neuspesna_prihlaseni"
    __table_args__ = (Index("ix_neuspesna_prihlaseni_ip_cas", "ip", "cas"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    cas: Mapped[datetime] = _cas()


class Dokument(Zaklad):
    __tablename__ = "dokumenty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nazev: Mapped[str] = mapped_column(String(200), nullable=False)
    nazev_souboru: Mapped[str] = mapped_column(String(255), nullable=False)
    druh: Mapped[DruhDokumentu] = mapped_column(
        Enum(DruhDokumentu, name="druh_dokumentu"), nullable=False
    )
    pojisteni: Mapped[Pojisteni] = mapped_column(Enum(Pojisteni, name="pojisteni"), nullable=False)
    # Komu dokument patří (smlouva, hlášení). U podmínek prázdné.
    # Podle tohohle sloupce se bude filtrovat už při vyhledávání (fáze 3).
    klient_id: Mapped[int | None] = mapped_column(
        ForeignKey("uzivatele.id", ondelete="RESTRICT"), index=True
    )
    typ_obsahu: Mapped[str] = mapped_column(String(50), nullable=False)
    velikost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Soubor je přímo v databázi (Jakub, 4. 11. 2026): žádný placený disk
    # na Railway a záloha databáze zálohuje i soubory. Načítá se jen na vyžádání.
    obsah: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    nahral_id: Mapped[int] = mapped_column(ForeignKey("uzivatele.id"), nullable=False)
    nahrano: Mapped[datetime] = _cas()

    # Čtení (krok 2A): běží na pozadí po nahrání, výsledek je v tabulkách
    # `stranky` a `uryvky`. Skeny čte Claude jen jednou — výsledek se uloží.
    stav_cteni: Mapped[StavCteni] = mapped_column(
        Enum(StavCteni, name="stav_cteni"), nullable=False, server_default=StavCteni.CEKA.value
    )
    # Krátký důvod pro člověka; nikdy obsah dokumentu.
    chyba_cteni: Mapped[str | None] = mapped_column(String(200))
    precteno: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pocet_stran: Mapped[int | None] = mapped_column(Integer)

    klient: Mapped[Uzivatel | None] = relationship(foreign_keys=[klient_id], lazy="joined")


class Strana(Zaklad):
    """Text jedné stránky dokumentu — z PDF, nebo přepsaný Claudem (OCR)."""

    __tablename__ = "stranky"
    __table_args__ = (UniqueConstraint("dokument_id", "cislo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dokument_id: Mapped[int] = mapped_column(
        ForeignKey("dokumenty.id", ondelete="CASCADE"), nullable=False
    )
    cislo: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ocr: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Uryvek(Zaklad):
    """Kousek textu, ve kterém bude asistent hledat. Nikdy nepřesahuje
    stránku, takže jde vždy citovat „dokument, strana N“."""

    __tablename__ = "uryvky"
    __table_args__ = (
        Index("ix_uryvky_dokument_poradi", "dokument_id", "poradi"),
        Index("ix_uryvky_slova_ts", "slova_ts", postgresql_using="gin"),
        Index(
            "ix_uryvky_vektor",
            "vektor",
            postgresql_using="hnsw",
            postgresql_ops={"vektor": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dokument_id: Mapped[int] = mapped_column(
        ForeignKey("dokumenty.id", ondelete="CASCADE"), nullable=False
    )
    strana: Mapped[int] = mapped_column(Integer, nullable=False)
    poradi: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nejbližší nadpis nad úryvkem („Článek 5 – Spoluúčast“), i z předchozí strany.
    nadpis: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Vyhledávání (krok 2B, app/hledani.py). Otisk významu z lokálního modelu;
    # prázdný jen u úryvků z doby před 2B, doplní se po startu aplikace.
    vektor: Mapped[list[float] | None] = mapped_column(Vector(256))
    # Text malými písmeny bez diakritiky a z něj slova pro fulltext.
    slova: Mapped[str | None] = mapped_column(Text)
    slova_ts = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(slova, ''))", persisted=True)
    )


class Audit(Zaklad):
    """Historie: kdo co udělal. Zapisuje se ve stejné transakci jako změna.
    Nikdy sem nepatří heslo, token ani obsah dokumentu."""

    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cas: Mapped[datetime] = _cas()
    uzivatel_id: Mapped[int | None] = mapped_column(
        ForeignKey("uzivatele.id", ondelete="SET NULL"), index=True
    )
    akce: Mapped[str] = mapped_column(String(50), nullable=False)
    podrobnosti: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DotazAi(Zaklad):
    """Jeden dotaz na asistenta — jen kvůli denním limitům a hlídání útraty
    (krok 3A). **Text otázky ani odpovědi se neukládá.** Řádek vzniká před
    voláním Anthropicu (rezervace v limitu); když volání selže, smaže se."""

    __tablename__ = "dotazy_ai"
    __table_args__ = (Index("ix_dotazy_ai_den_uzivatel", "den", "uzivatel_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uzivatel_id: Mapped[int | None] = mapped_column(ForeignKey("uzivatele.id", ondelete="SET NULL"))
    cas: Mapped[datetime] = _cas()
    # Pražský den, ke kterému se dotaz počítá (limit platí od půlnoci v Praze).
    den: Mapped[date] = mapped_column(Date, nullable=False)
    # Jen v ukázce: otisk adresy návštěvníka (SHA-256 s dnem, ne adresa sama)
    # pro limit na návštěvníka. Mimo ukázku prázdné.
    navstevnik: Mapped[str | None] = mapped_column(String(64), index=True)
    vstupni_tokeny: Mapped[int | None] = mapped_column(Integer)
    vystupni_tokeny: Mapped[int | None] = mapped_column(Integer)


class StavVytezeni(enum.StrEnum):
    """Jak daleko je vytěžení údajů z hlášení škody (krok 4B)."""

    CEKA = "CEKA"
    PROBIHA = "PROBIHA"
    HOTOVO = "HOTOVO"
    CEKA_NA_AI = "CEKA_NA_AI"
    CHYBA = "CHYBA"


NAZVY_STAVU_VYTEZENI = {
    StavVytezeni.CEKA: "Čeká na vytěžení",
    StavVytezeni.PROBIHA: "Vytěžuje se…",
    StavVytezeni.HOTOVO: "Vytěženo",
    StavVytezeni.CEKA_NA_AI: "Čeká na AI",
    StavVytezeni.CHYBA: "Chyba vytěžení",
}


class Vytezeni(Zaklad):
    """Údaje vytěžené Claudem z přepisu hlášení škody (krok 4B). Jeden řádek
    na hlášení. `navrh` je to, co navrhla AI — člověk ho v kroku 4C opraví
    a potvrdí; návrh sám se nepřepisuje, jen novým vytěžením."""

    __tablename__ = "vytezeni"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dokument_id: Mapped[int] = mapped_column(
        ForeignKey("dokumenty.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stav: Mapped[StavVytezeni] = mapped_column(
        Enum(StavVytezeni, name="stav_vytezeni"), nullable=False, server_default=StavVytezeni.CEKA.value
    )
    # Ověřený tvar app.vytezeni.UdajeHlaseni; prázdné, dokud není hotovo.
    navrh: Mapped[dict | None] = mapped_column(JSON)
    # Krátký důvod pro člověka; nikdy obsah dokumentu.
    chyba: Mapped[str | None] = mapped_column(String(200))
    vytezeno: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vstupni_tokeny: Mapped[int | None] = mapped_column(Integer)
    vystupni_tokeny: Mapped[int | None] = mapped_column(Integer)
    # Kontrola člověkem (krok 4C). `udaje` = údaje po opravě pracovníkem
    # likvidace (stejný tvar jako `navrh`); prázdné, dokud na ně nikdo
    # nesáhl. Návrh AI zůstává, aby šla měřit přesnost AI i po kontrole.
    udaje: Mapped[dict | None] = mapped_column(JSON)
    potvrzeno: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    potvrdil_id: Mapped[int | None] = mapped_column(ForeignKey("uzivatele.id", ondelete="SET NULL"))
    potvrdil: Mapped[Uzivatel | None] = relationship(foreign_keys=[potvrdil_id], lazy="joined")
    # Zvýší se při každé změně — dva lidé si tak nepřepíšou opravy potichu.
    verze: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)

    @property
    def stav_kontroly(self) -> "StavKontroly | None":  # noqa: F821 — definováno níž
        if self.potvrzeno is not None:
            return StavKontroly.POTVRZENO
        if self.udaje is not None:
            return StavKontroly.ROZPRACOVANO
        if self.navrh is not None:
            return StavKontroly.CEKA
        return None


class StavKontroly(enum.StrEnum):
    """Kontrola vytěžených údajů člověkem (krok 4C). Odvozuje se z řádku
    `vytezeni`, v databázi zvlášť není."""

    CEKA = "CEKA"
    ROZPRACOVANO = "ROZPRACOVANO"
    POTVRZENO = "POTVRZENO"


NAZVY_STAVU_KONTROLY = {
    StavKontroly.CEKA: "Čeká na kontrolu",
    StavKontroly.ROZPRACOVANO: "Rozpracováno",
    StavKontroly.POTVRZENO: "Potvrzeno",
}


class UkazkaStav(Zaklad):
    """Kdy naposledy proběhla obnova živé ukázky (krok 6A). Jediný řádek
    (id = 1); obnova proběhne nejvýš jednou za pražský den."""

    __tablename__ = "ukazka_stav"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    posledni_obnova: Mapped[date] = mapped_column(Date, nullable=False)
