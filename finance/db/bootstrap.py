"""Create the local schema and seed editable default categories."""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from finance.db.base import Base
from finance.db.session import PROJECT_ROOT, create_db_engine, create_session_factory
from finance.models import Category

DEFAULT_CATEGORIES_PATH = PROJECT_ROOT / "config" / "default_categories.yaml"


def create_schema(engine: Engine) -> None:
    # Importing finance.models above registers every mapped table in Base.metadata.
    Base.metadata.create_all(engine)


def seed_categories(session: Session, config_path: Path = DEFAULT_CATEGORIES_PATH) -> int:
    """Insert categories not yet present; never overwrite user edits."""

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    created = 0
    for parent_spec in data["categories"]:
        parent, was_created = _get_or_create_category(session, parent_spec, parent_id=None)
        created += int(was_created)
        for child_spec in parent_spec.get("children", []):
            _, was_created = _get_or_create_category(session, child_spec, parent_id=parent.id)
            created += int(was_created)
    session.commit()
    return created


def _get_or_create_category(
    session: Session, spec: dict, parent_id: int | None
) -> tuple[Category, bool]:
    category = session.scalar(select(Category).where(Category.slug == spec["slug"]))
    if category is not None:
        return category, False

    category = Category(
        name=spec["name"],
        slug=spec["slug"],
        parent_id=parent_id,
        is_living_cost=spec.get("is_living_cost", False),
        is_essential=spec.get("is_essential", False),
        is_recurring=spec.get("is_recurring", False),
        is_extraordinary_default=spec.get("is_extraordinary_default", False),
    )
    session.add(category)
    session.flush()
    return category, True


def initialize_database(database_url: str | None = None) -> Engine:
    engine = create_db_engine(database_url)
    create_schema(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        seed_categories(session)
    return engine
