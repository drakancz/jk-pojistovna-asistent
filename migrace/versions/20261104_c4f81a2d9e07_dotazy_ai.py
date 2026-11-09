"""dotazy na asistenta: denní limity a hlídání útraty

Revize: c4f81a2d9e07
Předchozí: b7d3e9a15c42
Vytvořeno: 2026-11-04

Text otázky ani odpovědi se neukládá — jen kdo, kdy a kolik tokenů.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f81a2d9e07"
down_revision: str | Sequence[str] | None = "b7d3e9a15c42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dotazy_ai",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uzivatel_id", sa.Integer(), nullable=True),
        sa.Column("cas", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("den", sa.Date(), nullable=False),
        sa.Column("vstupni_tokeny", sa.Integer(), nullable=True),
        sa.Column("vystupni_tokeny", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["uzivatel_id"], ["uzivatele.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dotazy_ai_den_uzivatel", "dotazy_ai", ["den", "uzivatel_id"])


def downgrade() -> None:
    op.drop_index("ix_dotazy_ai_den_uzivatel", table_name="dotazy_ai")
    op.drop_table("dotazy_ai")
