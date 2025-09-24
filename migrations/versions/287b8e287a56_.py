"""Migrate amendementen.created_by -> indiener_id; tidy motie

Revision ID: 287b8e287a56
Revises: aa6d5689cec3
Create Date: 2025-09-24 09:38:51.843135
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "287b8e287a56"
down_revision = "aa6d5689cec3"
branch_labels = None
depends_on = None


def _find_fk_name(table: str, constrained_col: str, referred_table: str):
    """Zoek de naam van een bestaande foreign key (handig als de naam per backend verschilt)."""
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        cols = fk.get("constrained_columns") or []
        if constrained_col in cols and fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def upgrade():
    # --- AMENDEMENTEN ---
    # Doel: kolom 'created_by' vervangen door 'indiener_id' met FK naar user.id
    with op.batch_alter_table("amendementen", schema=None) as batch_op:
        # 1) nieuwe kolom toevoegen als NULLABLE (anders faalt het op bestaande data)
        batch_op.add_column(sa.Column("indiener_id", sa.Integer(), nullable=True))

    # 2) bestaande data overzetten created_by -> indiener_id
    #    (alleen als 'created_by' bestaat)
    conn = op.get_bind()
    insp = inspect(conn)
    amend_cols = {c["name"] for c in insp.get_columns("amendementen")}
    if "created_by" in amend_cols:
        conn.execute(sa.text("UPDATE amendementen SET indiener_id = created_by"))

        # 3) bestaande FK op created_by droppen (zoek naam dynamisch)
        fk_name = _find_fk_name("amendementen", "created_by", "user")
        if fk_name:
            with op.batch_alter_table("amendementen", schema=None) as batch_op:
                batch_op.drop_constraint(fk_name, type_="foreignkey")

        # 4) oude kolom verwijderen
        with op.batch_alter_table("amendementen", schema=None) as batch_op:
            batch_op.drop_column("created_by")

    # 5) nieuwe FK op indiener_id aanmaken (met vaste naam)
    with op.batch_alter_table("amendementen", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_amendementen_indiener_id_user_id",
            "user",
            ["indiener_id"],
            ["id"],
            ondelete=None,  # pas aan indien gewenst: "CASCADE"/"SET NULL"
        )
        # 6) indiener_id nu NOT NULL maken (na vullen + FK)
        batch_op.alter_column(
            "indiener_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    # --- MOTIE ---
    # bestaande alembic-gen: indiener_id nullable True; drop Field13 (als aanwezig)
    with op.batch_alter_table("motie", schema=None) as batch_op:
        batch_op.alter_column("indiener_id", existing_type=sa.Integer(), nullable=True)

    # 'Field13' alleen droppen als die bestaat (veilig bij diverse omgevingen)
    motie_cols = {c["name"] for c in insp.get_columns("motie")}
    if "Field13" in motie_cols:
        with op.batch_alter_table("motie", schema=None) as batch_op:
            batch_op.drop_column("Field13")


def downgrade():
    # --- MOTIE ---
    # Herstel Field13 en maak indiener_id weer NOT NULL (zoals in auto-gen)
    with op.batch_alter_table("motie", schema=None) as batch_op:
        # alleen toevoegen als afwezig
        # (batch_alter_table maakt hercreatie op sqlite makkelijker, maar dubbel toevoegen wil je niet)
        batch_op.add_column(sa.Column("Field13", sa.Integer(), nullable=True))
        batch_op.alter_column("indiener_id", existing_type=sa.Integer(), nullable=False)

    # --- AMENDEMENTEN ---
    # We draaien de mapping terug: maak created_by aan, kopieer data terug, zet FK en drop indiener_id
    with op.batch_alter_table("amendementen", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Integer(), nullable=True))

    # Data terugzetten indien kolom bestaat
    conn = op.get_bind()
    insp = inspect(conn)
    amend_cols = {c["name"] for c in insp.get_columns("amendementen")}
    if "created_by" in amend_cols and "indiener_id" in amend_cols:
        conn.execute(sa.text("UPDATE amendementen SET created_by = indiener_id"))

    # Drop FK op indiener_id
    fk_name = _find_fk_name("amendementen", "indiener_id", "user")
    if fk_name:
        with op.batch_alter_table("amendementen", schema=None) as batch_op:
            batch_op.drop_constraint(fk_name, type_="foreignkey")

    # Zet FK op created_by (met vaste naam) en maak hem NOT NULL
    with op.batch_alter_table("amendementen", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_amendementen_created_by_user_id",
            "user",
            ["created_by"],
            ["id"],
            ondelete=None,
        )
        batch_op.alter_column(
            "created_by",
            existing_type=sa.Integer(),
            nullable=False,
        )
        # Tot slot: drop indiener_id
        batch_op.drop_column("indiener_id")
