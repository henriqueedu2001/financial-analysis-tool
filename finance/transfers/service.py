"""Reversible internal-transfer suggestions and manual confirmation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from finance.importers.hashing import normalized_description
from finance.models import (
    ClassificationSource,
    ReviewState,
    Transaction,
    TransactionEdit,
    TransactionNature,
    TransferMatch,
    TransferMatchState,
)


class TransferError(ValueError):
    pass


@dataclass(frozen=True)
class TransferSuggestion:
    outgoing_transaction_id: int
    incoming_transaction_id: int
    confidence_basis_points: int
    date_distance_days: int
    ambiguous: bool
    rationale: str


def find_transfer_suggestions(
    session: Session, *, max_date_distance_days: int = 3
) -> list[TransferSuggestion]:
    transactions = session.scalars(
        select(Transaction)
        .options(joinedload(Transaction.account))
        .where(Transaction.amount_cents != 0)
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    confirmed = session.scalars(
        select(TransferMatch).where(TransferMatch.state == TransferMatchState.CONFIRMED)
    ).all()
    used = {
        transaction_id
        for match in confirmed
        for transaction_id in (
            match.outgoing_transaction_id,
            match.incoming_transaction_id,
        )
    }
    rejected_pairs = set(
        session.execute(
            select(
                TransferMatch.outgoing_transaction_id,
                TransferMatch.incoming_transaction_id,
            ).where(TransferMatch.state == TransferMatchState.REJECTED)
        ).all()
    )

    outgoing_by_amount: dict[int, list[Transaction]] = defaultdict(list)
    incoming_by_amount: dict[int, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        if transaction.id in used:
            continue
        if transaction.amount_cents < 0:
            outgoing_by_amount[abs(transaction.amount_cents)].append(transaction)
        elif transaction.amount_cents > 0:
            incoming_by_amount[transaction.amount_cents].append(transaction)

    candidates: list[tuple[Transaction, Transaction, int]] = []
    for amount, outgoing_rows in outgoing_by_amount.items():
        for outgoing in outgoing_rows:
            for incoming in incoming_by_amount.get(amount, []):
                distance = abs((incoming.transaction_date - outgoing.transaction_date).days)
                pair = (outgoing.id, incoming.id)
                if (
                    outgoing.account_id != incoming.account_id
                    and distance <= max_date_distance_days
                    and pair not in rejected_pairs
                ):
                    candidates.append((outgoing, incoming, distance))

    outgoing_counts = Counter(outgoing.id for outgoing, _, _ in candidates)
    incoming_counts = Counter(incoming.id for _, incoming, _ in candidates)
    suggestions: list[TransferSuggestion] = []
    for outgoing, incoming, distance in candidates:
        similarity = SequenceMatcher(
            None,
            normalized_description(outgoing.original_description),
            normalized_description(incoming.original_description),
        ).ratio()
        confidence = min(9900, int(7000 - distance * 500 + similarity * 2000))
        ambiguous = outgoing_counts[outgoing.id] > 1 or incoming_counts[incoming.id] > 1
        rationale = (
            f"valor absoluto igual; sinais opostos; contas diferentes; "
            f"distância de {distance} dia(s); similaridade textual {similarity:.0%}"
        )
        suggestions.append(
            TransferSuggestion(
                outgoing.id,
                incoming.id,
                confidence,
                distance,
                ambiguous,
                rationale,
            )
        )
    return sorted(
        suggestions,
        key=lambda item: (
            item.ambiguous,
            -item.confidence_basis_points,
            item.outgoing_transaction_id,
        ),
    )


def confirm_transfer_match(
    session: Session,
    outgoing_transaction_id: int,
    incoming_transaction_id: int,
    *,
    confidence_basis_points: int = 10000,
    rationale: str | None = None,
) -> TransferMatch:
    outgoing = session.get(Transaction, outgoing_transaction_id)
    incoming = session.get(Transaction, incoming_transaction_id)
    if outgoing is None or incoming is None:
        raise TransferError("uma das movimentações não existe")
    if outgoing.amount_cents >= 0 or incoming.amount_cents <= 0:
        raise TransferError("a saída deve ser negativa e a entrada positiva")
    if outgoing.account_id == incoming.account_id:
        raise TransferError("transferências internas exigem contas diferentes")
    if abs(outgoing.amount_cents) != incoming.amount_cents:
        raise TransferError("as duas pontas precisam ter valores absolutos iguais")
    if not 0 <= confidence_basis_points <= 10000:
        raise TransferError("confiança deve estar entre 0 e 10000 pontos-base")

    conflicting = session.scalar(
        select(TransferMatch).where(
            TransferMatch.state == TransferMatchState.CONFIRMED,
            or_(
                TransferMatch.outgoing_transaction_id.in_(
                    (outgoing_transaction_id, incoming_transaction_id)
                ),
                TransferMatch.incoming_transaction_id.in_(
                    (outgoing_transaction_id, incoming_transaction_id)
                ),
            ),
        )
    )
    if conflicting is not None and (
        conflicting.outgoing_transaction_id != outgoing_transaction_id
        or conflicting.incoming_transaction_id != incoming_transaction_id
    ):
        raise TransferError("uma das movimentações já pertence a outra transferência")

    match = session.scalar(
        select(TransferMatch).where(
            TransferMatch.outgoing_transaction_id == outgoing_transaction_id,
            TransferMatch.incoming_transaction_id == incoming_transaction_id,
        )
    )
    if match is None:
        match = TransferMatch(
            outgoing_transaction_id=outgoing_transaction_id,
            incoming_transaction_id=incoming_transaction_id,
        )
        session.add(match)
    match.state = TransferMatchState.CONFIRMED
    match.confidence_basis_points = confidence_basis_points
    match.manually_confirmed = True
    match.rationale = rationale
    _set_transfer_state(outgoing, True, "Associação manual de transferência", session)
    _set_transfer_state(incoming, True, "Associação manual de transferência", session)
    session.commit()
    return match


def reject_transfer_match(session: Session, match_id: int) -> TransferMatch:
    match = session.get(TransferMatch, match_id)
    if match is None:
        raise TransferError("associação não encontrada")
    outgoing = session.get(Transaction, match.outgoing_transaction_id)
    incoming = session.get(Transaction, match.incoming_transaction_id)
    match.state = TransferMatchState.REJECTED
    match.manually_confirmed = True
    if outgoing is not None:
        _set_transfer_state(outgoing, False, "Desassociação manual de transferência", session)
    if incoming is not None:
        _set_transfer_state(incoming, False, "Desassociação manual de transferência", session)
    session.commit()
    return match


def mark_transaction_as_transfer(
    session: Session, transaction_id: int, *, is_transfer: bool
) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise TransferError("movimentação não encontrada")
    if not is_transfer:
        confirmed_match = session.scalar(
            select(TransferMatch.id).where(
                TransferMatch.state == TransferMatchState.CONFIRMED,
                or_(
                    TransferMatch.outgoing_transaction_id == transaction_id,
                    TransferMatch.incoming_transaction_id == transaction_id,
                ),
            )
        )
        if confirmed_match is not None:
            raise TransferError("desassocie o par confirmado antes de remover a marcação")
    _set_transfer_state(transaction, is_transfer, "Marcação manual de transferência", session)
    session.commit()
    return transaction


def _set_transfer_state(
    transaction: Transaction, is_transfer: bool, reason: str, session: Session
) -> None:
    before = {
        "is_internal_transfer": transaction.is_internal_transfer,
        "nature": transaction.nature.value,
        "classification_source": transaction.classification_source.value,
        "manual_classification_locked": transaction.manual_classification_locked,
    }
    transaction.is_internal_transfer = is_transfer
    transaction.nature = (
        TransactionNature.TRANSFER
        if is_transfer
        else (
            TransactionNature.INCOME if transaction.amount_cents > 0 else TransactionNature.EXPENSE
        )
    )
    transaction.classification_source = ClassificationSource.MANUAL
    transaction.manual_classification_locked = True
    transaction.review_state = ReviewState.REVIEWED
    after = {
        "is_internal_transfer": transaction.is_internal_transfer,
        "nature": transaction.nature.value,
        "classification_source": transaction.classification_source.value,
        "manual_classification_locked": transaction.manual_classification_locked,
    }
    changes = {
        field: {"before": before[field], "after": after[field]}
        for field in before
        if before[field] != after[field]
    }
    if changes:
        session.add(TransactionEdit(transaction=transaction, changes=changes, reason=reason))
