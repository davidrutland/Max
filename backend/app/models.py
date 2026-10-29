import datetime

from sqlalchemy import ForeignKey, String, Text, Boolean, Integer, DateTime, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.crypto import EncryptedString
from app.database import Base


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"
    # sqlite_autoincrement: deleted ids are NEVER reused (monotonically increasing).
    # id==1 is the super admin (first sign-up), protected by business rule (no demote/block/delete).
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")  # "admin" | "user"
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Single-row (id=1) application settings."""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default="ollama")  # "ollama" | "openai"
    host: Mapped[str] = mapped_column(String(255), default="")  # for ollama; empty for openai
    port: Mapped[int] = mapped_column(Integer, default=11434)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # openai (e.g. https://api.openai.com/v1)
    # Encrypted at rest (crypto.py); plaintext on the attribute. Wider than the plaintext it
    # holds because a Fernet token is ~40% longer than its input plus a fixed header — SQLite
    # does not enforce the length, but the declaration should not lie.
    api_key: Mapped[str | None] = mapped_column(EncryptedString(1000), nullable=True)  # openai
    wol_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    wol_target: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class McpServer(Base):
    """A remote MCP server. Its tools are registered into the shared tool registry under
    `source="mcp:<id>"` (see tools/mcp_client.py).

    sqlite_autoincrement (unlike `servers`): a deleted id is never reused, so a stale probe
    entry can never be inherited by a different server that happens to get the same id —
    the bug `routers/servers.py` has to defend against with `_invalidate` on DELETE.
    """
    __tablename__ = "mcp_servers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique because it becomes the tool-name namespace (`mcp__<slug>__<tool>`); two servers
    # with the same name would produce colliding tool names.
    name: Mapped[str] = mapped_column(String(100), unique=True)
    url: Mapped[str] = mapped_column(String(500))
    # "http" = Streamable HTTP, "sse" = the older HTTP+SSE transport (Linear still uses it).
    transport: Mapped[str] = mapped_column(String(10), default="http")
    # The secret lives in its own column, deliberately NOT inside `headers`: `exclude_unset`
    # partial updates cannot express "this one value of the map is unchanged", so a map
    # round-tripped through the edit form with a masked secret would wipe it.
    # Encrypted at rest (crypto.py); plaintext on the attribute. See the width note on
    # Server.api_key.
    secret: Mapped[str | None] = mapped_column(EncryptedString(2000), nullable=True)
    # Which header carries `secret` — servers differ: "Authorization" (GitHub, needs the
    # "Bearer " prefix) vs "CONTEXT7_API_KEY" (Context7, raw value).
    secret_header: Mapped[str] = mapped_column(String(100), default="Authorization")
    secret_prefix: Mapped[str] = mapped_column(String(20), default="Bearer ")
    # Extra non-secret headers, e.g. {"X-MCP-Readonly": "true", "X-MCP-Toolsets": "repos"}.
    headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # {tool name as the server advertises it: "off" | "auto" | "approve"}. Tools not listed
    # fall back to a default derived from readOnlyHint: read-only → "auto", mutating → "off"
    # (fail-safe — an admin has to opt in, so an upgrade changes nothing).
    # Kept here rather than in config/tools.yml: round-tripping that file through a YAML dump
    # would destroy the comments that document it.
    tool_modes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, default=1)
    title: Mapped[str] = mapped_column(String(255), default="New Chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Compaction (compaction.py): a summary standing in for every message up to and including
    # summary_upto_id. The messages themselves are kept. context_mode "full" ignores the summary.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_upto_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_mode: Mapped[str] = mapped_column(String(10), default="compact")  # "compact" | "full"
    # "agent": tool steps are persisted with each reply and replayed on later turns (#91).
    # "chat": today's behaviour, where only the reply's text reaches the history.
    mode: Mapped[str] = mapped_column(String(10), default="chat")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    images: Mapped[list | None] = mapped_column(JSON, nullable=True)  # base64 data-URI listesi (vision)
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{name, text}] document attachments
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    server_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Agent mode: the turn's tool traffic in provider shape, in order — assistant tool-call
    # turns and tool results (+ display fields `ok`, `approval`). `content` is the final answer.
    steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chat: Mapped["Chat"] = relationship(back_populates="messages")
    artifact_references: Mapped[list["ArtifactReference"]] = relationship(lazy="selectin", viewonly=True)


class ChatContextBinding(Base):
    """Per-chat persistence ownership; absent for pre-existing legacy chats.

    Router alias and connection port do not establish model identity.
    Identity immutability is enforced by application policy in a later patch.
    """
    __tablename__ = "chat_context_bindings"

    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True)
    backend_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    router_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    model_path: Mapped[str] = mapped_column(Text, nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mmproj_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mmproj_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    backend_build: Mapped[str] = mapped_column(String(255), nullable=False)
    runtime_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tool_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(1000), unique=True, nullable=True)
    snapshot_status: Mapped[str] = mapped_column(String(20), nullable=False, default="absent")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    """Immutable published blob; the opaque ID is also its storage filename."""
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactReference(Base):
    """A message owns a reference; forks get separate references to the same blob."""
    __tablename__ = "artifact_references"

    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True)
    artifact: Mapped["Artifact"] = relationship(lazy="joined", viewonly=True)
