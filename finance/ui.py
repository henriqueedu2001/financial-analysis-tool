"""Small shared helpers for the Streamlit shell."""

from dataclasses import dataclass

from sqlalchemy import func, select

from finance.db import create_session_factory, initialize_database
from finance.models import Account, Category


@dataclass(frozen=True)
class FoundationStatus:
    account_count: int
    category_count: int


def load_foundation_status() -> FoundationStatus:
    engine = initialize_database()
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        account_count = session.scalar(select(func.count()).select_from(Account)) or 0
        category_count = session.scalar(select(func.count()).select_from(Category)) or 0
    return FoundationStatus(account_count=account_count, category_count=category_count)
