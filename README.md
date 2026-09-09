# Análise financeira pessoal

Pipeline local e reproduzível para consolidar extratos bancários, classificar
movimentações com revisão humana e produzir uma análise estática. Não é um
aplicativo web.

## Privacidade

Todo o conteúdo de `data/` é local e ignorado pelo Git, exceto os `.gitkeep` que
preservam diretórios vazios. Extratos, descrições, classificações, saldos e
relatórios pessoais nunca devem ser versionados.

## Instalação

Requer Python 3.11 ou superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Fase 1: inventário e normalização

Os OFX originais ficam imutáveis, separados por instituição, em
`data/sources/`. Execute:

```bash
python scripts/01_inventory_sources.py
python scripts/02_build_canonical.py
```

O primeiro comando gera `data/derived/source_inventory.csv`. O segundo gera:

* `data/derived/transactions_canonical.csv`, com todas as contas identificadas;
* `data/derived/statement_snapshots.csv`, com os saldos informados pelos bancos;
* `data/derived/coverage_summary.csv`, com períodos e meses sem movimentações;
* `data/derived/reconciliation.csv`, com a conferência entre saldos sucessivos.

Os comandos são idempotentes. Arquivos repetidos são reconhecidos por SHA-256 e
movimentações sobrepostas são deduplicadas por conta e identificador bancário.
Nenhum arquivo OFX é alterado.

## Testes

```bash
pytest
ruff check .
```
