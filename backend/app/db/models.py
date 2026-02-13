from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    # MVP: store the first connected account. Later: add user_id.
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    token_json: Mapped[str] = mapped_column(Text)
