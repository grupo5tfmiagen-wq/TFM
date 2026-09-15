"""add sexo and anio_nacimiento to cv_documents

Revision ID: 2532f21401a6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# identificadores de revision, usados por Alembic.
revision: str = '2532f21401a6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Datos demograficos para auditoria de sesgos (pagina Metricas de la UI
    # Streamlit). Deliberadamente nullable y sin backfill aqui: se rellenan
    # a mano (o desde el script de carga de datos de demo), nunca inferidos
    # automaticamente a partir de otros campos como el nombre.
    op.add_column('cv_documents', sa.Column('sexo', sa.String(length=20), nullable=True))
    op.add_column('cv_documents', sa.Column('anio_nacimiento', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('cv_documents', 'anio_nacimiento')
    op.drop_column('cv_documents', 'sexo')
