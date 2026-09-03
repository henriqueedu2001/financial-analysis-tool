"""CRUD operations for deterministic local classification rules."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from finance.models import (
    Category,
    ClassificationRule,
    RuleMatchType,
    TransactionNature,
)


class ClassificationRuleError(ValueError):
    pass


def _validate_rule(
    session: Session,
    *,
    name: str,
    match_type: RuleMatchType,
    pattern: str,
    category_id: int | None,
    nature: TransactionNature | None,
    mark_extraordinary: bool | None,
    priority: int,
) -> tuple[str, str]:
    clean_name = name.strip()
    clean_pattern = pattern.strip()
    if not clean_name or not clean_pattern:
        raise ClassificationRuleError("nome e padrão são obrigatórios")
    if priority < 0:
        raise ClassificationRuleError("prioridade deve ser zero ou positiva")
    if category_id is None and nature is None and mark_extraordinary is None:
        raise ClassificationRuleError("a regra precisa executar ao menos uma classificação")
    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None or not category.is_active:
            raise ClassificationRuleError("categoria ativa não encontrada")
    if match_type is RuleMatchType.DESCRIPTION_REGEX:
        try:
            re.compile(clean_pattern)
        except re.error as exc:
            raise ClassificationRuleError(f"expressão regular inválida: {exc}") from exc
    return clean_name, clean_pattern


def create_classification_rule(
    session: Session,
    *,
    name: str,
    match_type: RuleMatchType,
    pattern: str,
    category_id: int | None = None,
    nature: TransactionNature | None = None,
    mark_extraordinary: bool | None = None,
    priority: int = 100,
    commit: bool = True,
) -> ClassificationRule:
    clean_name, clean_pattern = _validate_rule(
        session,
        name=name,
        match_type=match_type,
        pattern=pattern,
        category_id=category_id,
        nature=nature,
        mark_extraordinary=mark_extraordinary,
        priority=priority,
    )
    rule = ClassificationRule(
        name=clean_name,
        match_type=match_type,
        pattern=clean_pattern,
        category_id=category_id,
        nature=nature,
        mark_extraordinary=mark_extraordinary,
        priority=priority,
    )
    session.add(rule)
    if commit:
        session.commit()
    else:
        session.flush()
    return rule


def update_classification_rule(
    session: Session,
    rule_id: int,
    *,
    name: str,
    match_type: RuleMatchType,
    pattern: str,
    category_id: int | None,
    nature: TransactionNature | None,
    mark_extraordinary: bool | None,
    priority: int,
    is_active: bool,
) -> ClassificationRule:
    rule = session.get(ClassificationRule, rule_id)
    if rule is None:
        raise ClassificationRuleError("regra não encontrada")
    clean_name, clean_pattern = _validate_rule(
        session,
        name=name,
        match_type=match_type,
        pattern=pattern,
        category_id=category_id,
        nature=nature,
        mark_extraordinary=mark_extraordinary,
        priority=priority,
    )
    rule.name = clean_name
    rule.match_type = match_type
    rule.pattern = clean_pattern
    rule.category_id = category_id
    rule.nature = nature
    rule.mark_extraordinary = mark_extraordinary
    rule.priority = priority
    rule.is_active = is_active
    session.commit()
    return rule
