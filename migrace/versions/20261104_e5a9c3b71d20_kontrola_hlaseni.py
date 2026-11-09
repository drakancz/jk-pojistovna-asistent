"""kontrola vytěžených údajů člověkem (krok 4C)

Revize: e5a9c3b71d20
Předchozí: bb99192f0ee6
Vytvořeno: 2026-11-04

Opravené údaje, kdo a kdy potvrdil, verze proti souběžným opravám.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a9c3b71d20"
down_revision: str | Sequence[str] | None = "bb99192f0ee6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vytezeni", sa.Column("udaje", sa.JSON(), nullable=True))
    op.add_column("vytezeni", sa.Column("potvrzeno", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vytezeni", sa.Column("potvrdil_id", sa.Integer(), nullable=True))
    op.add_column("vytezeni", sa.Column("verze", sa.Integer(), server_default="0", nullable=False))
    op.create_foreign_key(
        "vytezeni_potvrdil_id_fkey", "vytezeni", "uzivatele", ["potvrdil_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("vytezeni_potvrdil_id_fkey", "vytezeni", type_="foreignkey")
    op.drop_column("vytezeni", "verze")
    op.drop_column("vytezeni", "potvrdil_id")
    op.drop_column("vytezeni", "potvrzeno")
    op.drop_column("vytezeni", "udaje")
