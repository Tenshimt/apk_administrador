"""phase4: decimal quantities, product unit and m2_per_box

Revision ID: a1b2c3d4e5f6
Revises: bd0c04a0cc2d
Create Date: 2026-10-19 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bd0c04a0cc2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # products: add unit, m2_per_box; change stock columns to Numeric
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('unit', sa.Enum('m2', 'box', 'unit', name='product_unit'), nullable=False, server_default='unit'))
        batch_op.add_column(sa.Column('m2_per_box', sa.Numeric(8, 3), nullable=True))
        batch_op.alter_column('stock_quantity', type_=sa.Numeric(12, 3), existing_nullable=False)
        batch_op.alter_column('low_stock_threshold', type_=sa.Numeric(12, 3), existing_nullable=False)

    # sale_items: add requested_m2; change quantity to Numeric
    with op.batch_alter_table('sale_items') as batch_op:
        batch_op.add_column(sa.Column('requested_m2', sa.Numeric(12, 3), nullable=True))
        batch_op.alter_column('quantity', type_=sa.Numeric(12, 3), existing_nullable=False)

    # stock_movements: change quantity_change to Numeric
    with op.batch_alter_table('stock_movements') as batch_op:
        batch_op.alter_column('quantity_change', type_=sa.Numeric(12, 3), existing_nullable=False)

    # purchase_order_items: change quantity columns to Numeric
    with op.batch_alter_table('purchase_order_items') as batch_op:
        batch_op.alter_column('quantity_ordered', type_=sa.Numeric(12, 3), existing_nullable=False)
        batch_op.alter_column('quantity_received', type_=sa.Numeric(12, 3), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('purchase_order_items') as batch_op:
        batch_op.alter_column('quantity_received', type_=sa.Integer(), existing_nullable=False)
        batch_op.alter_column('quantity_ordered', type_=sa.Integer(), existing_nullable=False)

    with op.batch_alter_table('stock_movements') as batch_op:
        batch_op.alter_column('quantity_change', type_=sa.Integer(), existing_nullable=False)

    with op.batch_alter_table('sale_items') as batch_op:
        batch_op.alter_column('quantity', type_=sa.Integer(), existing_nullable=False)
        batch_op.drop_column('requested_m2')

    with op.batch_alter_table('products') as batch_op:
        batch_op.alter_column('low_stock_threshold', type_=sa.Integer(), existing_nullable=False)
        batch_op.alter_column('stock_quantity', type_=sa.Integer(), existing_nullable=False)
        batch_op.drop_column('m2_per_box')
        batch_op.drop_column('unit')
