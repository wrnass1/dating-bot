from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import User
from app.schemas import TelegramUserUpsertIn, TelegramUserUpsertOut


app = FastAPI(title="Dating Bot API", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    # For stage 2 we keep it simple: auto-create the minimal table set.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/users/telegram/upsert", response_model=TelegramUserUpsertOut)
def upsert_telegram_user(payload: TelegramUserUpsertIn, db: Session = Depends(get_db)) -> TelegramUserUpsertOut:
    existing = db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if existing is None:
        user = User(
            telegram_id=payload.telegram_id,
            username=payload.username,
            first_name=payload.first_name,
            language=payload.language,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return TelegramUserUpsertOut(user_id=str(user.id), is_new=True)

    changed = False
    for field in ("username", "first_name", "language"):
        new_val = getattr(payload, field)
        if new_val is not None and getattr(existing, field) != new_val:
            setattr(existing, field, new_val)
            changed = True
    if changed:
        db.commit()

    return TelegramUserUpsertOut(user_id=str(existing.id), is_new=False)

