"""Editable hierarchical category repository."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from finance.models import Category


class CategoryError(ValueError):
    pass


def _slug_part(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", errors="ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")


def create_category(
    session: Session,
    *,
    name: str,
    parent_id: int | None = None,
    is_living_cost: bool = False,
    is_essential: bool = False,
    is_recurring: bool = False,
    is_extraordinary_default: bool = False,
) -> Category:
    clean_name = name.strip()
    if not clean_name:
        raise CategoryError("o nome da categoria é obrigatório")
    parent = session.get(Category, parent_id) if parent_id else None
    if parent_id and parent is None:
        raise CategoryError("categoria pai não encontrada")
    prefix = f"{parent.slug}-" if parent else ""
    base_slug = prefix + (_slug_part(clean_name) or "categoria")
    slug = base_slug
    suffix = 2
    while session.scalar(select(Category.id).where(Category.slug == slug)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    category = Category(
        name=clean_name,
        slug=slug,
        parent_id=parent_id,
        is_living_cost=is_living_cost,
        is_essential=is_essential,
        is_recurring=is_recurring,
        is_extraordinary_default=is_extraordinary_default,
    )
    session.add(category)
    session.commit()
    return category


def update_category(
    session: Session,
    category_id: int,
    *,
    name: str,
    is_living_cost: bool,
    is_essential: bool,
    is_recurring: bool,
    is_extraordinary_default: bool,
    is_active: bool,
) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise CategoryError("categoria não encontrada")
    clean_name = name.strip()
    if not clean_name:
        raise CategoryError("o nome da categoria é obrigatório")
    category.name = clean_name
    category.is_living_cost = is_living_cost
    category.is_essential = is_essential
    category.is_recurring = is_recurring
    category.is_extraordinary_default = is_extraordinary_default
    category.is_active = is_active
    session.commit()
    return category
