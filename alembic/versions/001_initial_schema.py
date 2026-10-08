"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. generation_jobs
    op.create_table(
        'generation_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_generation_jobs_status'), 'generation_jobs', ['status'], unique=False)

    # 2. recipients
    op.create_table(
        'recipients',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('event_name', sa.String(length=255), nullable=False),
        sa.Column('completion_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['generation_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_recipients_job_id'), 'recipients', ['job_id'], unique=False)
    op.create_index(op.f('ix_recipients_email'), 'recipients', ['email'], unique=False)
    op.create_index(op.f('ix_recipients_status'), 'recipients', ['status'], unique=False)

    # 3. certificates
    op.create_table(
        'certificates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('recipient_id', sa.Uuid(), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['recipient_id'], ['recipients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recipient_id'),
    )
    op.create_index(op.f('ix_certificates_recipient_id'), 'certificates', ['recipient_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_certificates_recipient_id'), table_name='certificates')
    op.drop_table('certificates')
    op.drop_index(op.f('ix_recipients_status'), table_name='recipients')
    op.drop_index(op.f('ix_recipients_email'), table_name='recipients')
    op.drop_index(op.f('ix_recipients_job_id'), table_name='recipients')
    op.drop_table('recipients')
    op.drop_index(op.f('ix_generation_jobs_status'), table_name='generation_jobs')
    op.drop_table('generation_jobs')
