"""initial schema

Revision ID: 868e195cb90f
Revises: 
Create Date: 2026-07-22 19:49:27.667370

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# identificadores de revision, usados por Alembic.
revision: str = '868e195cb90f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### comandos autogenerados por Alembic - por favor, ajustar! ###
    op.create_table('cases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_type', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('current_node_key', sa.String(length=150), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('dag_definitions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('graph_export', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('case_node_executions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('node_key', sa.String(length=150), nullable=False),
    sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('output_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('final_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('outcome', sa.String(length=100), nullable=False),
    sa.Column('consolidated_from', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('decided_by', sa.String(length=150), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id')
    )
    op.create_table('human_escalations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('node_execution_id', sa.UUID(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('assigned_to', sa.String(length=150), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['node_execution_id'], ['case_node_executions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('llm_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('node_execution_id', sa.UUID(), nullable=False),
    sa.Column('model_name', sa.String(length=150), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('raw_response', sa.Text(), nullable=True),
    sa.Column('structured_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('confidence', sa.Numeric(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['node_execution_id'], ['case_node_executions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rule_evaluations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('node_execution_id', sa.UUID(), nullable=False),
    sa.Column('rule_name', sa.String(length=150), nullable=False),
    sa.Column('result_bool', sa.Boolean(), nullable=True),
    sa.Column('score', sa.Numeric(), nullable=True),
    sa.Column('label', sa.String(length=150), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['node_execution_id'], ['case_node_executions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('validations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('node_execution_id', sa.UUID(), nullable=False),
    sa.Column('llm_decision_id', sa.UUID(), nullable=True),
    sa.Column('is_valid', sa.Boolean(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('requires_review', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['llm_decision_id'], ['llm_decisions.id'], ),
    sa.ForeignKeyConstraint(['node_execution_id'], ['case_node_executions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### fin comandos Alembic ###


def downgrade() -> None:
    # ### comandos autogenerados por Alembic - por favor, ajustar! ###
    op.drop_table('validations')
    op.drop_table('rule_evaluations')
    op.drop_table('llm_decisions')
    op.drop_table('human_escalations')
    op.drop_table('final_decisions')
    op.drop_table('case_node_executions')
    op.drop_table('dag_definitions')
    op.drop_table('cases')
    # ### fin comandos Alembic ###
