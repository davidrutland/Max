"""Database references for immutable published artifacts.

The database is authoritative: remove a blob only when no message references it.
Call cleanup after committing the transaction that removed message references.
"""
from sqlalchemy import select
from app import models
from app.artifact_store import remove


def link(db, message_id: int, artifact_id: str):
    """Attach an existing artifact to a persisted message (same transaction)."""
    message = db.get(models.Message, message_id)
    if message is None:
        raise ValueError('message does not exist')
    artifact = db.get(models.Artifact, artifact_id)
    if artifact is None:
        raise ValueError('artifact does not exist')
    if not db.get(models.ArtifactReference, (message_id, artifact_id)):
        db.add(models.ArtifactReference(message_id=message_id, artifact_id=artifact_id))


def orphan_ids(db):
    """Return blobs not referenced by any message; safe after cascading deletes."""
    return list(db.scalars(select(models.Artifact.id).outerjoin(
        models.ArtifactReference, models.Artifact.id == models.ArtifactReference.artifact_id
    ).where(models.ArtifactReference.artifact_id.is_(None))))


def reclaim(db, *, root=None):
    """Reclaim unreferenced blobs under SQLite's writer lock.

    A concurrent publisher cannot add a reference between the orphan check and
    removal. This function is called only after chat mutations have committed.
    """
    # An immediate transaction serializes this sweep with reference insertion.
    # Do not call with an existing transaction: callers must commit first.
    if db.in_transaction():
        raise RuntimeError("reclaim requires a fresh session after commit")
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    try:
        for identifier in orphan_ids(db):
            try:
                if root is None:
                    remove(identifier)
                else:
                    remove(identifier, root=root)
            except OSError:
                continue
            artifact = db.get(models.Artifact, identifier)
            if artifact is not None:
                db.delete(artifact)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def copy_references(db, source_message_id: int, target_message_id: int):
    for ref in db.scalars(select(models.ArtifactReference).where(
        models.ArtifactReference.message_id == source_message_id
    )):
        db.add(models.ArtifactReference(message_id=target_message_id, artifact_id=ref.artifact_id))
