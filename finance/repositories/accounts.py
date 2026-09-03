"""Small account repository for the local single-user application."""

from sqlalchemy.orm import Session

from finance.models import Account, AccountType, FinancialRole


def create_account(
    session: Session,
    *,
    name: str,
    institution: str | None,
    account_type: AccountType,
    financial_role: FinancialRole,
    currency: str = "BRL",
    include_in_tracked_wealth: bool = True,
    is_reserve: bool = False,
) -> Account:
    account = Account(
        name=name.strip(),
        institution=institution.strip() if institution else None,
        account_type=account_type,
        financial_role=financial_role,
        currency=currency.upper(),
        include_in_tracked_wealth=include_in_tracked_wealth,
        is_reserve=is_reserve,
    )
    session.add(account)
    session.commit()
    return account
