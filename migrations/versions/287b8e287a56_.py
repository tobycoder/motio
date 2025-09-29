"""Migrate amendementen.created_by -> indiener_id; tidy motie

Revision ID: 287b8e287a56
Revises: aa6d5689cec3
Create Date: 2025-09-24 09:38:51.843135
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from typing import Optional

# revision identifiers, used by Alembic.
revision = "287b8e287a56"
down_revision = "aa6d5689cec3"
branch_labels = None
depends_on = None


def _find_fk_name(table: str, constrained_col: str, referred_table: str) -> Optional[str]:
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        cols = fk.get("constrained_columns") or []
        if constrained_col in cols and fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    amend_cols = {c["name"] for c in insp.get_columns("amendementen")}
    if "indiener_id" not in amend_cols:
        with op.batch_alter_table("amendementen", schema=None) as batch_op:
            batch_op.add_column(sa.Column("indiener_id", sa.Integer(), nullable=True))
        amend_cols.add("indiener_id")

    if "created_by" in amend_cols:
        bind.execute(sa.text("UPDATE amendementen SET indiener_id = created_by"))
        fk_name = _find_fk_name("amendementen", "created_by", "user")
        if fk_name:
            with op.batch_alter_table("amendementen", schema=None) as batch_op:
                batch_op.drop_constraint(fk_name, type_="foreignkey")
        with op.batch_alter_table("amendementen", schema=None) as batch_op:
            batch_op.drop_column("created_by")
        amend_cols.discard("created_by")

    if "indiener_id" in amend_cols:
        fk_name = _find_fk_name("amendementen", "indiener_id", "user")
        with op.batch_alter_table("amendementen", schema=None) as batch_op:
            if not fk_name:
                batch_op.create_foreign_key(
                    "fk_amendementen_indiener_id_user_id",
                    "user",
                    ["indiener_id"],
                    ["id"],
                    ondelete=None,
                )
            batch_op.alter_column(
                "indiener_id",
                existing_type=sa.Integer(),
                nullable=False,
            )

    motie_cols = {c["name"] for c in insp.get_columns("motie")}
    if "indiener_id" in motie_cols:
        with op.batch_alter_table("motie", schema=None) as batch_op:
            batch_op.alter_column("indiener_id", existing_type=sa.Integer(), nullable=True)
    if "Field13" in motie_cols:
        with op.batch_alter_table("motie", schema=None) as batch_op:
            batch_op.drop_column("Field13")


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    with op.batch_alter_table("motie", schema=None) as batch_op:
        batch_op.add_column(sa.Column("Field13", sa.Integer(), nullable=True))
        batch_op.alter_column("indiener_id", existing_type=sa.Integer(), nullable=False)

    amend_cols = {c["name"] for c in insp.get_columns("amendementen")}
    if "created_by" not in amend_cols:
        with op.batch_alter_table("amendementen", schema=None) as batch_op:
            batch_op.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        amend_cols.add("created_by")

    if "created_by" in amend_cols and "indiener_id" in amend_cols:
        bind.execute(sa.text("UPDATE amendementen SET created_by = indiener_id"))

    fk_name = _find_fk_name("amendementen", "indiener_id", "user")
    with op.batch_alter_table("amendementen", schema=None) as batch_op:
        if fk_name:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_amendementen_created_by_user_id",
            "user",
            ["created_by"],
            ["id"],
            ondelete=None,
        )
        if "indiener_id" in amend_cols:
            batch_op.drop_column("indiener_id")
        batch_op.alter_column(
            "created_by",
            existing_type=sa.Integer(),
            nullable=False,
        )
