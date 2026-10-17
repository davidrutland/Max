"""Read-only, authenticated message search. No inference or database migrations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import auth, models
from app.database import get_db
from app.search_query import QuerySyntaxError, parse, matches

router = APIRouter(prefix='/api/search', tags=['search'])

@router.get('/messages')
def search_messages(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    try:
        expression = parse(q)
    except QuerySyntaxError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Restrict at SQL level before inspecting message content. Deliberately
    # scan until a lossless FTS5 candidate strategy is established.
    rows = (db.query(models.Message.id, models.Message.chat_id,
                     models.Message.role, models.Message.content,
                     models.Message.timestamp, models.Chat.title,
                     models.Chat.archived)
            .join(models.Chat, models.Chat.id == models.Message.chat_id)
            .filter(models.Chat.user_id == user.id)
            .order_by(models.Message.id.asc()))
    total = 0
    results = []
    for message_id, chat_id, role, content, timestamp, title, archived in rows:
        if not matches(expression, content or ''):
            continue
        if offset <= total < offset + limit:
            results.append({'message_id': message_id, 'chat_id': chat_id,
                            'role': role, 'content': content,
                            'timestamp': timestamp, 'chat_title': title,
                            'archived': bool(archived)})
        total += 1
    return {'total': total, 'results': results, 'limit': limit, 'offset': offset}
