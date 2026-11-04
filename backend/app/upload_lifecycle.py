"""Reclaim original uploads only when no surviving message references them."""
import datetime
import logging
from pathlib import Path

from app import models

log = logging.getLogger(__name__)


def referenced_ids(db, user_id):
    chat_ids = db.query(models.Chat.id).filter(models.Chat.user_id == user_id)
    result = set()
    for (attachments,) in db.query(models.Message.attachments).filter(models.Message.chat_id.in_(chat_ids)):
        for item in attachments or []:
            if isinstance(item, dict) and isinstance(item.get('upload_id'), str):
                result.add(item['upload_id'])
    return result


def reclaim(db, root: Path, user_id, *, stale_only=False, grace_hours=24, candidates=None):
    """Delete unreferenced uploads; for unsent uploads, wait for the grace period.

    Call after the message/chat deletion commits. Disk unlink failures are logged,
    leaving the DB record available for a later retry.
    """
    referenced = referenced_ids(db, user_id)
    cutoff = models.utcnow() - datetime.timedelta(hours=grace_hours)
    for record in db.query(models.IncomingUpload).filter_by(user_id=user_id).all():
        if (candidates is not None and record.id not in candidates) or record.id in referenced or (stale_only and record.created_at.replace(tzinfo=datetime.timezone.utc) > cutoff):
            continue
        try:
            (root / record.id).unlink(missing_ok=True)
        except OSError:
            log.exception('Unable to remove incoming upload %s', record.id)
            continue
        db.delete(record)
    db.commit()


def ids_in_chat(db, chat_id, from_message_id=None):
    query = db.query(models.Message.attachments).filter(models.Message.chat_id == chat_id)
    if from_message_id is not None:
        query = query.filter(models.Message.id >= from_message_id)
    return {item["upload_id"] for (atts,) in query for item in (atts or []) if isinstance(item, dict) and isinstance(item.get("upload_id"), str)}


def reclaim_after_change(db, user_id, candidates):
    from app.routers.uploads import ROOT
    reclaim(db, ROOT, user_id, candidates=candidates)


def remove_user_files(db, root, user_id):
    """Called after user deletion; removes any dangling upload blobs."""
    for record in db.query(models.IncomingUpload).filter_by(user_id=user_id).all():
        try:
            (root / record.id).unlink(missing_ok=True)
        except OSError:
            log.exception('Unable to remove incoming upload %s', record.id)
