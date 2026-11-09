"""živá ukázka (krok 6A): stav noční obnovy, limit na návštěvníka

Revize: ddf780676821
Předchozí: e5a9c3b71d20
Vytvořeno: 2026-11-08

Tabulka ukazka_stav (kdy naposledy proběhla obnova) a otisk adresy
návštěvníka u dotazů na asistenta (limit v ukázce).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'ddf780676821'
down_revision: str | Sequence[str] | None = 'e5a9c3b71d20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('ukazka_stav',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('posledni_obnova', sa.Date(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('dotazy_ai', sa.Column('navstevnik', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_dotazy_ai_navstevnik'), 'dotazy_ai', ['navstevnik'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dotazy_ai_navstevnik'), table_name='dotazy_ai')
    op.drop_column('dotazy_ai', 'navstevnik')
    op.drop_table('ukazka_stav')
