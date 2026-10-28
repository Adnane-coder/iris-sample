"""create iris_staging schema and transformer specs tables (Task 099)

Revision ID: c099f0e1a7b2
Revises: b18ad888465f
Create Date: 2026-10-28 09:00:00.000000

Staging only: this migration never touches the iris_core schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c099f0e1a7b2'
down_revision: Union[str, Sequence[str], None] = 'b18ad888465f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = 'iris_staging'


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(f'CREATE SCHEMA IF NOT EXISTS {SCHEMA}')

    op.create_table(
        'transformer_specs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spec_key', sa.String(length=64), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('source_kind', sa.String(length=20), nullable=False),
        sa.Column('is_illustrative', sa.Boolean(), nullable=False),
        sa.Column('source_document', sa.String(length=255), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('source_version', sa.String(length=64), nullable=True),
        sa.Column('source_retrieved_on', sa.Date(), nullable=True),
        sa.Column('source_file_sha256', sa.String(length=64), nullable=False),
        sa.Column('source_row_number', sa.Integer(), nullable=False),
        sa.Column('country_code', sa.String(length=2), nullable=True),
        sa.Column('spatial_scope', sa.String(length=50), nullable=True),
        sa.Column('voltage_class', sa.String(length=40), nullable=False),
        sa.Column('voltage_hv_kv', sa.Numeric(precision=8, scale=3, asdecimal=False), nullable=False),
        sa.Column('voltage_lv_kv', sa.Numeric(precision=8, scale=3, asdecimal=False), nullable=False),
        sa.Column('nominal_mva', sa.Numeric(precision=9, scale=3, asdecimal=False), nullable=False),
        sa.Column('impedance_uk_percent', sa.Numeric(precision=5, scale=2, asdecimal=False), nullable=False),
        sa.Column('cooling_class', sa.String(length=20), nullable=True),
        sa.Column('vector_group', sa.String(length=20), nullable=True),
        sa.Column('top_oil_rise_limit_k', sa.Numeric(precision=5, scale=1, asdecimal=False), nullable=True),
        sa.Column('winding_avg_rise_limit_k', sa.Numeric(precision=5, scale=1, asdecimal=False), nullable=True),
        sa.Column('hotspot_limit_c', sa.Numeric(precision=5, scale=1, asdecimal=False), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('quality_flags', sa.JSON(), nullable=True),
        sa.Column('raw_record', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('spec_key', name='uq_transformer_specs_spec_key'),
        schema=SCHEMA,
    )
    op.create_index('idx_transformer_specs_source_id', 'transformer_specs', ['source_id'], unique=False, schema=SCHEMA)
    op.create_index('idx_transformer_specs_voltage', 'transformer_specs', ['voltage_hv_kv', 'voltage_lv_kv'], unique=False, schema=SCHEMA)

    op.create_table(
        'transformer_spec_rejects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('source_file_sha256', sa.String(length=64), nullable=False),
        sa.Column('source_row_number', sa.Integer(), nullable=False),
        sa.Column('reason_code', sa.String(length=40), nullable=False),
        sa.Column('reason_detail', sa.Text(), nullable=True),
        sa.Column('raw_record', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'source_file_sha256', 'source_row_number', 'reason_code', name='uq_transformer_spec_rejects_row'),
        schema=SCHEMA,
    )
    op.create_index('idx_transformer_spec_rejects_source_id', 'transformer_spec_rejects', ['source_id'], unique=False, schema=SCHEMA)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_transformer_spec_rejects_source_id', table_name='transformer_spec_rejects', schema=SCHEMA)
    op.drop_table('transformer_spec_rejects', schema=SCHEMA)
    op.drop_index('idx_transformer_specs_voltage', table_name='transformer_specs', schema=SCHEMA)
    op.drop_index('idx_transformer_specs_source_id', table_name='transformer_specs', schema=SCHEMA)
    op.drop_table('transformer_specs', schema=SCHEMA)
    # The schema is dropped only if empty (no CASCADE): never destroys other data.
    op.execute(f'DROP SCHEMA IF EXISTS {SCHEMA}')
