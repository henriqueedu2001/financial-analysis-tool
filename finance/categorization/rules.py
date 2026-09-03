"""Deterministic local classification rule evaluation."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from finance.importers.hashing import normalized_description
from finance.models import (
    ClassificationRule,
    ClassificationSource,
    ReviewState,
    RuleMatchType,
    Transaction,
    TransactionNature,
)


def rule_matches(rule: ClassificationRule, transaction: Transaction) -> bool:
    if not rule.is_active:
        return False
    pattern = rule.pattern.strip()
    if not pattern:
        return False
    description = transaction.normalized_description or normalized_description(
        transaction.original_description
    )
    if rule.match_type is RuleMatchType.DESCRIPTION_CONTAINS:
        return normalized_description(pattern) in description
    if rule.match_type is RuleMatchType.DESCRIPTION_REGEX:
        return re.search(pattern, transaction.original_description, flags=re.IGNORECASE) is not None
    if rule.match_type is RuleMatchType.COUNTERPARTY_CONTAINS:
        return bool(
            transaction.counterparty
            and normalized_description(pattern) in normalized_description(transaction.counterparty)
        )
    return False


def apply_first_matching_rule(
    session: Session, transaction: Transaction
) -> ClassificationRule | None:
    """Apply only the highest-priority match, unless a manual correction is locked."""

    if transaction.manual_classification_locked:
        return None
    rules = session.scalars(
        select(ClassificationRule)
        .options(joinedload(ClassificationRule.category))
        .where(ClassificationRule.is_active.is_(True))
        .order_by(ClassificationRule.priority.asc(), ClassificationRule.id.asc())
    )
    for rule in rules:
        if rule.category is not None and not rule.category.is_active:
            continue
        if not rule_matches(rule, transaction):
            continue
        if rule.category_id is not None:
            transaction.category_id = rule.category_id
        if rule.nature is not None:
            transaction.nature = rule.nature
        if rule.mark_extraordinary is not None:
            transaction.is_extraordinary = rule.mark_extraordinary
        transaction.classification_source = ClassificationSource.RULE
        transaction.review_state = (
            ReviewState.REVIEWED
            if transaction.category_id is not None
            and transaction.nature is not TransactionNature.UNCLASSIFIED
            else ReviewState.PENDING
        )
        return rule
    return None
