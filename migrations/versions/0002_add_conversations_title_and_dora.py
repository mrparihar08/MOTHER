"""add_conversations_title_and_dora

Revision ID: 0002_conversations_title_dora
Revises: 0001_initial_schema
Create Date: 2026-10-31 16:32:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '0002_conversations_title_dora'
down_revision: Union[str, Sequence[str], None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # 1. Version-controlled migration for conversation title column (replaces raw SQL ALTER TABLE)
    table_names = inspector.get_table_names()
    if 'conversations' in table_names:
        columns = [c['name'] for c in inspector.get_columns('conversations')]
        if 'title' not in columns:
            with op.batch_alter_table('conversations', schema=None) as batch_op:
                batch_op.add_column(sa.Column('title', sa.String(length=255), nullable=True))

    # 2. Add dora_assessments table
    if 'dora_assessments' not in table_names:
        op.create_table(
            'dora_assessments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('symptoms', sa.Text(), nullable=False),
            sa.Column('predicted_disease', sa.String(length=200), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('urgency', sa.String(length=50), nullable=True),
            sa.Column('specialist', sa.String(length=100), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('dora_assessments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_dora_assessments_id'), ['id'], unique=False)
            batch_op.create_index(batch_op.f('ix_dora_assessments_user_id'), ['user_id'], unique=False)

    # 3. Add saved_presentations table
    if 'saved_presentations' not in table_names:
        op.create_table(
            'saved_presentations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('presentation_id', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=True),
            sa.Column('state_json', sa.Text(), nullable=False),
            sa.Column('file_path', sa.String(length=512), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('saved_presentations', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_saved_presentations_id'), ['id'], unique=False)
            batch_op.create_index(batch_op.f('ix_saved_presentations_presentation_id'), ['presentation_id'], unique=True)
            batch_op.create_index(batch_op.f('ix_saved_presentations_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    table_names = inspector.get_table_names()

    if 'saved_presentations' in table_names:
        op.drop_table('saved_presentations')

    if 'dora_assessments' in table_names:
        op.drop_table('dora_assessments')

    if 'conversations' in table_names:
        columns = [c['name'] for c in inspector.get_columns('conversations')]
        if 'title' in columns:
            with op.batch_alter_table('conversations', schema=None) as batch_op:
                batch_op.drop_column('title')
