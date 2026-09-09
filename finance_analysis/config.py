import tomllib
from pathlib import Path

from finance_analysis.models import AccountDefinition


def load_accounts(path: Path) -> tuple[AccountDefinition, ...]:
    with path.open("rb") as stream:
        document = tomllib.load(stream)

    accounts = tuple(AccountDefinition(**item) for item in document.get("accounts", []))
    if not accounts:
        raise ValueError(f"Nenhuma conta configurada em {path}")
    if len({item.account_id for item in accounts}) != len(accounts):
        raise ValueError("account_id duplicado na configuração")
    return accounts


def account_for_path(
    relative_path: Path,
    accounts: tuple[AccountDefinition, ...],
) -> AccountDefinition:
    if not relative_path.parts:
        raise ValueError("Caminho de fonte vazio")
    matches = [item for item in accounts if relative_path.parts[0] == item.path_prefix]
    if len(matches) != 1:
        raise ValueError(f"Fonte sem conta inequívoca: {relative_path}")
    return matches[0]
