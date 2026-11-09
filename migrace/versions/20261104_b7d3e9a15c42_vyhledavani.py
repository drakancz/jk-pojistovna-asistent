"""vyhledávání: pgvector, otisk významu a fulltext u úryvků

Revize: b7d3e9a15c42
Předchozí: a2c7e1f04b31
Vytvořeno: 2026-11-04

Rozšíření `vector` smí na sdíleném Postgresu zapnout jen správce
serveru (není „trusted“). Před prvním nasazením ho správce zapne jednou
v databázi asistenta (CREATE EXTENSION vector); tady
`IF NOT EXISTS` pak projde bez dalších práv. Místně a v testech je
uživatel databáze správcem, takže ho migrace zapne sama.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "b7d3e9a15c42"
down_revision: str | Sequence[str] | None = "a2c7e1f04b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Úryvky přečtené dřív dostanou otisk po startu aplikace (hledani.priprav).
    op.add_column("uryvky", sa.Column("vektor", Vector(256), nullable=True))
    op.add_column("uryvky", sa.Column("slova", sa.Text(), nullable=True))
    op.add_column(
        "uryvky",
        sa.Column(
            "slova_ts",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(slova, ''))", persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_uryvky_slova_ts", "uryvky", ["slova_ts"], postgresql_using="gin")
    op.create_index(
        "ix_uryvky_vektor",
        "uryvky",
        ["vektor"],
        postgresql_using="hnsw",
        postgresql_ops={"vektor": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_uryvky_vektor", table_name="uryvky")
    op.drop_index("ix_uryvky_slova_ts", table_name="uryvky")
    op.drop_column("uryvky", "slova_ts")
    op.drop_column("uryvky", "slova")
    op.drop_column("uryvky", "vektor")
    # Rozšíření vector zůstává — mohou ho používat i jiné tabulky.
