"""add cv_documents and job_postings tables

Revision ID: a1b2c3d4e5f6
Revises: 868e195cb90f
Create Date: 2026-08-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# identificadores de revision, usados por Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '868e195cb90f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### comandos autogenerados por Alembic - por favor, ajustar! ###
    
    # Crear tabla job_postings
    op.create_table('job_postings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('external_id', sa.String(length=150), nullable=False),
        sa.Column('titulo', sa.String(length=300), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('requisitos_minimos', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('requisitos_deseables', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('habilidades_requeridas', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('idiomas_requeridos', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('experiencia_minima_anios', sa.Integer(), nullable=True),
        sa.Column('formacion_minima', sa.String(length=200), nullable=True),
        sa.Column('ubicacion', sa.String(length=200), nullable=True),
        sa.Column('tipo_contrato', sa.String(length=100), nullable=True),
        sa.Column('salario_min', sa.Numeric(), nullable=True),
        sa.Column('salario_max', sa.Numeric(), nullable=True),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.Column('fecha_publicacion', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fecha_cierre', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id')
    )
    op.create_index(op.f('ix_job_postings_external_id'), 'job_postings', ['external_id'], unique=True)
    
    # Crear tabla cv_documents
    op.create_table('cv_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.String(length=150), nullable=False),
        sa.Column('candidate_name', sa.String(length=300), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=True),
        sa.Column('original_format', sa.String(length=50), nullable=True),
        sa.Column('idioma', sa.String(length=10), nullable=True),
        sa.Column('texto_extraido', sa.Text(), nullable=True),
        sa.Column('experiencia', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('formacion', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('habilidades_tecnicas', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('idiomas', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('certificaciones', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cv_documents_candidate_id'), 'cv_documents', ['candidate_id'], unique=False)
    
    # Añadir foreign keys a la tabla cases
    op.add_column('cases', sa.Column('cv_document_id', sa.UUID(), nullable=True))
    op.add_column('cases', sa.Column('job_posting_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_cases_cv_document_id', 'cases', 'cv_documents', ['cv_document_id'], ['id'])
    op.create_foreign_key('fk_cases_job_posting_id', 'cases', 'job_postings', ['job_posting_id'], ['id'])
    
    # ### fin comandos Alembic ###


def downgrade() -> None:
    # ### comandos autogenerados por Alembic - por favor, ajustar! ###
    
    # Eliminar foreign keys de cases
    op.drop_constraint('fk_cases_job_posting_id', 'cases', type_='foreignkey')
    op.drop_constraint('fk_cases_cv_document_id', 'cases', type_='foreignkey')
    op.drop_column('cases', 'job_posting_id')
    op.drop_column('cases', 'cv_document_id')
    
    # Eliminar tablas
    op.drop_index(op.f('ix_cv_documents_candidate_id'), table_name='cv_documents')
    op.drop_table('cv_documents')
    op.drop_index(op.f('ix_job_postings_external_id'), table_name='job_postings')
    op.drop_table('job_postings')
    
    # ### fin comandos Alembic ###
