"""vytěžení údajů z hlášení škody (krok 4B)

Revize: bb99192f0ee6
Předchozí: c4f81a2d9e07
Vytvořeno: 2026-11-04

Jeden řádek na hlášení: návrh údajů od AI, stav a spotřeba tokenů.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bb99192f0ee6"
down_revision: str | Sequence[str] | None = "c4f81a2d9e07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAV = sa.Enum("CEKA", "PROBIHA", "HOTOVO", "CEKA_NA_AI", "CHYBA", name="stav_vytezeni")


def upgrade() -> None:
    op.create_table(
        "vytezeni",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dokument_id", sa.Integer(), nullable=False),
        sa.Column("stav", STAV, server_default="CEKA", nullable=False),
        sa.Column("navrh", sa.JSON(), nullable=True),
        sa.Column("chyba", sa.String(length=200), nullable=True),
        sa.Column("vytezeno", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vstupni_tokeny", sa.Integer(), nullable=True),
        sa.Column("vystupni_tokeny", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["dokument_id"], ["dokumenty.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dokument_id"),
    )


def downgrade() -> None:
    op.drop_table("vytezeni")
    STAV.drop(op.get_bind(), checkfirst=True)
