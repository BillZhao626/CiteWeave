"""Pinned Dense identities and durable experimental index provenance.

OperationRow records model identity; IndexRow records owned physical collections.
No derived index can change an immutable version's active E5 publication.
"""

E5 = dict(
    model="intfloat/multilingual-e5-small",
    revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
    dimension=384,
    mode="dense_only",
    max_tokens=256,
    normalize=True,
    query_prefix="query: ",
    document_prefix="passage: ",
)
BGE = dict(
    model="BAAI/bge-m3",
    revision="5617a9f61b028005a4858fdac845db406aefb181",
    dimension=1024,
    mode="dense_only",
    max_tokens=256,
    normalize=True,
    query_prefix="",
    document_prefix="",
)
MODELS = {"e5-small": E5, "bge-m3": BGE}


def embedding_identity(key="e5-small"):
    if key not in MODELS:
        raise ValueError("unknown_embedding")
    return dict(MODELS[key])


def resolve_experiment_bindings(db, workspace, version_ids, model, captured=None):
    """Must be called under governance_lock with authorized READY version IDs."""
    from fastapi import HTTPException
    from sqlalchemy import select

    from citeweave.domain import IndexRow, OperationRow

    if captured is not None and set(captured) != {str(v) for v in version_ids}:
        raise HTTPException(409, "embedding_snapshot_scope_mismatch")
    result = {}
    operations = list(
        db.scalars(
            select(OperationRow)
            .where(
                OperationRow.workspace_id == workspace,
                OperationRow.kind == "embedding_index",
                OperationRow.status == "COMPLETED",
            )
            .order_by(OperationRow.created_at.desc(), OperationRow.id)
        )
    )
    for version_id in version_ids:
        wanted = captured.get(str(version_id)) if captured is not None else None
        matches = [
            op
            for op in operations
            if op.target == str(version_id)
            and op.detail.get("embedding") == model
            and (wanted is None or op.detail.get("collection") == wanted)
        ]
        if not matches:
            raise HTTPException(409, "embedding_index_not_ready")
        name = matches[0].detail["collection"]
        row = db.get(IndexRow, name)
        if (
            not row
            or row.workspace_id != workspace
            or row.version_id != version_id
            or row.state != "EXPERIMENT_READY"
        ):
            raise HTTPException(409, "embedding_index_not_ready")
        result[str(version_id)] = name
    return result
