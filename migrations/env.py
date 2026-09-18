from alembic import context

from citeweave.db import engine
from citeweave.domain import Base

with engine().connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_object=lambda obj, name, type_, reflected, compare_to: (
            not (type_ == "table" and reflected and not name.startswith(("cw1_", "cw2_")))
        ),
    )
    with context.begin_transaction():
        context.run_migrations()
