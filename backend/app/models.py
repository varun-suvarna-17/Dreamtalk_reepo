from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def now_utc():
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    emotion: Mapped[str] = mapped_column(String(40), default="neutral")
    intent: Mapped[str] = mapped_column(String(60), default="conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
