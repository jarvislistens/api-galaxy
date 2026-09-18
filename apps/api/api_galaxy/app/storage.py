"""Persistence: SQLite for records, the filesystem for documents.

Graphs are JSON documents that get read whole and written whole, so they live as files
under the project directory rather than in the database. SQLite holds the things you
query — projects, scenarios, decisions, jobs, settings — and the decision log, which is
append-only by construction: there is no update path for it anywhere in the codebase.
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from api_galaxy.app.settings import Settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    source_kind: Mapped[str] = mapped_column(String(32), default="upload")
    spec_fingerprint: Mapped[str] = mapped_column(String(80), default="")
    app_version: Mapped[str] = mapped_column(String(32), default="")
    enrichment_label: Mapped[str] = mapped_column(String(64), default="none")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    scenarios: Mapped[list[ScenarioRecord]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source_kind": self.source_kind,
            "spec_fingerprint": self.spec_fingerprint,
            "app_version": self.app_version,
            "enrichment_label": self.enrichment_label,
            "is_demo": self.is_demo,
            "stats": self.stats or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ScenarioRecord(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    project: Mapped[ProjectRecord] = relationship(back_populates="scenarios")


class DecisionRecordRow(Base):
    """Append-only audit log. Nothing in the codebase updates or deletes a row here."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_template_version: Mapped[str] = mapped_column(String(32), default="")
    task: Mapped[str] = mapped_column(String(32), default="")
    action: Mapped[str] = mapped_column(String(32), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    editor: Mapped[str] = mapped_column(String(64), default="local-user")
    payload_fingerprint: Mapped[str] = mapped_column(String(80), default="")
    accepted_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_references: Mapped[list] = mapped_column(JSON, default=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "provider": self.provider,
            "model": self.model,
            "prompt_template_version": self.prompt_template_version,
            "task": self.task,
            "action": self.action,
            "subject": self.subject,
            "editor": self.editor,
            "payload_fingerprint": self.payload_fingerprint,
            "accepted_payload": self.accepted_payload or {},
            "source_references": self.source_references or [],
        }


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SettingRecord(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str] = mapped_column(String(64), default="local-user")


class ExportRecord(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    format: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[str] = mapped_column(String(120), default="project")
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "format": self.format,
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "scope": self.scope,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# --------------------------------------------------------------------------------------


class Storage:
    """Owns the database session factory and the on-disk project layout."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self.engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.migrate()

    def migrate(self) -> None:
        """Create any missing tables. SQLite plus `create_all` is the whole migration
        story for a single-user local app; the schema version lives in `settings`."""
        Base.metadata.create_all(self.engine)
        with self.session() as session:
            existing = session.get(SettingRecord, "schema_version")
            if existing is None:
                session.add(SettingRecord(key="schema_version", value={"version": 1}))

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = Session(self.engine, future=True)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- filesystem ----------------------------------------------------------------

    def project_dir(self, project_id: str) -> Path:
        safe = "".join(ch for ch in project_id if ch.isalnum() or ch in "-_")
        directory = self.settings.projects_dir / safe
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def write_document(self, project_id: str, name: str, payload: Any) -> Path:
        path = self.project_dir(project_id) / name
        text = payload if isinstance(payload, str) else json.dumps(payload, default=str, indent=1)
        path.write_text(text, encoding="utf-8")
        return path

    def read_document(self, project_id: str, name: str) -> Any | None:
        path = self.project_dir(project_id) / name
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            return json.loads(text)
        return text

    def write_export(self, project_id: str, filename: str, data: bytes) -> Path:
        directory = self.settings.exports_dir / project_id
        directory.mkdir(parents=True, exist_ok=True)
        safe = Path(filename).name.replace("..", "_")
        path = directory / safe
        path.write_bytes(data)
        return path

    def delete_project_files(self, project_id: str) -> None:
        for directory in (
            self.settings.projects_dir / project_id,
            self.settings.exports_dir / project_id,
        ):
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)

    # -- records -------------------------------------------------------------------

    def list_projects(self) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(
                select(ProjectRecord).order_by(ProjectRecord.updated_at.desc())
            ).all()
            return [row.to_dict() for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.session() as session:
            row = session.get(ProjectRecord, project_id)
            return row.to_dict() if row else None

    def upsert_project(self, **fields: Any) -> dict[str, Any]:
        with self.session() as session:
            row = session.get(ProjectRecord, fields["id"])
            if row is None:
                row = ProjectRecord(**fields)
                session.add(row)
            else:
                for key, value in fields.items():
                    setattr(row, key, value)
            session.flush()
            return row.to_dict()

    def delete_project(self, project_id: str) -> bool:
        with self.session() as session:
            row = session.get(ProjectRecord, project_id)
            if row is None:
                return False
            session.delete(row)
        self.delete_project_files(project_id)
        return True

    def record_decision(self, **fields: Any) -> dict[str, Any]:
        with self.session() as session:
            row = DecisionRecordRow(id=fields.pop("id", f"dec:{uuid.uuid4().hex[:12]}"), **fields)
            session.add(row)
            session.flush()
            return row.to_dict()

    def list_decisions(self, project_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(
                select(DecisionRecordRow)
                .where(DecisionRecordRow.project_id == project_id)
                .order_by(DecisionRecordRow.timestamp.desc())
                .limit(limit)
            ).all()
            return [row.to_dict() for row in rows]

    def save_scenario(self, scenario_id: str, project_id: str, name: str, description: str,
                      payload: dict[str, Any]) -> None:
        with self.session() as session:
            row = session.get(ScenarioRecord, scenario_id)
            if row is None:
                session.add(
                    ScenarioRecord(
                        id=scenario_id,
                        project_id=project_id,
                        name=name,
                        description=description,
                        payload=payload,
                    )
                )
            else:
                row.name = name
                row.description = description
                row.payload = payload

    def list_scenarios(self, project_id: str) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(
                select(ScenarioRecord)
                .where(ScenarioRecord.project_id == project_id)
                .order_by(ScenarioRecord.updated_at.desc())
            ).all()
            return [
                {
                    "id": r.id,
                    "project_id": r.project_id,
                    "name": r.name,
                    "description": r.description,
                    "payload": r.payload,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]

    def delete_scenario(self, scenario_id: str) -> bool:
        with self.session() as session:
            row = session.get(ScenarioRecord, scenario_id)
            if row is None:
                return False
            session.delete(row)
            return True

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.session() as session:
            row = session.get(SettingRecord, key)
            return row.value if row else default

    def set_setting(self, key: str, value: Any, *, updated_by: str = "local-user") -> Any:
        with self.session() as session:
            row = session.get(SettingRecord, key)
            if row is None:
                session.add(SettingRecord(key=key, value=value, updated_by=updated_by))
            else:
                row.value = value
                row.updated_by = updated_by
            return value

    def record_export(self, **fields: Any) -> dict[str, Any]:
        with self.session() as session:
            row = ExportRecord(**fields)
            session.add(row)
            session.flush()
            return row.to_dict()

    def list_exports(self, project_id: str) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = session.scalars(
                select(ExportRecord)
                .where(ExportRecord.project_id == project_id)
                .order_by(ExportRecord.created_at.desc())
            ).all()
            return [row.to_dict() for row in rows]

    def get_export(self, export_id: str) -> ExportRecord | None:
        with self.session() as session:
            row = session.get(ExportRecord, export_id)
            if row is None:
                return None
            session.expunge(row)
            return row

    def clear_all(self) -> dict[str, int]:
        """Settings → 'Clear everything'. Removes projects, exports and caches on disk."""
        counts = {"projects": 0, "exports": 0, "decisions": 0}
        with self.session() as session:
            counts["projects"] = len(session.scalars(select(ProjectRecord)).all())
            counts["exports"] = len(session.scalars(select(ExportRecord)).all())
            counts["decisions"] = len(session.scalars(select(DecisionRecordRow)).all())
            for model in (ExportRecord, DecisionRecordRow, ScenarioRecord, JobRecord, ProjectRecord):
                for row in session.scalars(select(model)).all():
                    session.delete(row)
        for directory in (self.settings.projects_dir, self.settings.exports_dir):
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
        self.settings.ensure_dirs()
        return counts
