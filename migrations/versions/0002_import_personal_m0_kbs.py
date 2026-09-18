"""Preserve the personal M0 starter catalog; no former project tables are read."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if not sa.inspect(connection).has_table("cw_knowledge_bases"):
        return
    rows = connection.execute(sa.text("SELECT * FROM cw_knowledge_bases")).mappings()
    for row in rows:
        values = dict(row)
        values["fingerprint"] = hashlib.sha256(
            json.dumps(
                {"name": row["name"], "description": row["description"]}, ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
        connection.execute(
            sa.text("""INSERT INTO cw1_knowledge_bases
            (id,workspace_id,name,description,status,key,fingerprint,created_at,updated_at)
            VALUES (:id,:workspace_id,:name,:description,:status,:key,:fingerprint,:created_at,:created_at)
            ON CONFLICT DO NOTHING"""),
            values,
        )


def downgrade():
    # Imported personal data remains owned by its original IDs. No destructive reversal.
    pass
