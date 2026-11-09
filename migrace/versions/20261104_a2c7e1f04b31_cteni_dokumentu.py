"""čtení dokumentů: stránky, úryvky, stav čtení, pojištění OBECNE

Revize: a2c7e1f04b31
Předchozí: d11fb3cdad87
Vytvořeno: 2026-11-04

Psáno ručně: autogenerate neumí přidat hodnotu do existujícího typu enum
a u add_column nový typ enum nezaloží.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a2c7e1f04b31"
down_revision: str | Sequence[str] | None = "d11fb3cdad87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAV = postgresql.ENUM(
    "CEKA", "CTE_SE", "PRECTENO", "CEKA_NA_OCR", "CHYBA", name="stav_cteni", create_type=False
)


def upgrade() -> None:
    op.execute("ALTER TYPE pojisteni ADD VALUE IF NOT EXISTS 'OBECNE'")

    STAV.create(op.get_bind(), checkfirst=True)
    # Dokumenty nahrané před tímhle krokem zůstanou „čeká“ a přečtou se
    # po startu aplikace.
    op.add_column("dokumenty", sa.Column("stav_cteni", STAV, nullable=False, server_default="CEKA"))
    op.add_column("dokumenty", sa.Column("chyba_cteni", sa.String(length=200), nullable=True))
    op.add_column("dokumenty", sa.Column("precteno", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dokumenty", sa.Column("pocet_stran", sa.Integer(), nullable=True))

    op.create_table(
        "stranky",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dokument_id", sa.Integer(), nullable=False),
        sa.Column("cislo", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("ocr", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["dokument_id"], ["dokumenty.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dokument_id", "cislo"),
    )
    op.create_table(
        "uryvky",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dokument_id", sa.Integer(), nullable=False),
        sa.Column("strana", sa.Integer(), nullable=False),
        sa.Column("poradi", sa.Integer(), nullable=False),
        sa.Column("nadpis", sa.String(length=200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["dokument_id"], ["dokumenty.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uryvky_dokument_poradi", "uryvky", ["dokument_id", "poradi"])


def downgrade() -> None:
    op.drop_index("ix_uryvky_dokument_poradi", table_name="uryvky")
    op.drop_table("uryvky")
    op.drop_table("stranky")
    op.drop_column("dokumenty", "pocet_stran")
    op.drop_column("dokumenty", "precteno")
    op.drop_column("dokumenty", "chyba_cteni")
    op.drop_column("dokumenty", "stav_cteni")
    STAV.drop(op.get_bind(), checkfirst=True)
    # Hodnota OBECNE v typu pojisteni zůstává — Postgres hodnotu z enum
    # odebrat neumí a nikomu nevadí.
