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
python3 -m pip install --upgrade pip
python3 -m pip install -e '.[dev]'
```

## Fase 1: inventário e normalização

Os OFX originais ficam imutáveis, separados por instituição, em
`data/sources/`. Execute:

```bash
python3 scripts/01_inventory_sources.py
python3 scripts/02_build_canonical.py
```

O primeiro comando gera `data/derived/source_inventory.csv`. O segundo gera:

* `data/derived/transactions_canonical.csv`, com todas as contas identificadas;
* `data/derived/statement_snapshots.csv`, com os saldos informados pelos bancos;
* `data/derived/coverage_summary.csv`, com períodos e meses sem movimentações;
* `data/derived/reconciliation.csv`, com a conferência entre saldos sucessivos.

Os comandos são idempotentes. Arquivos repetidos são reconhecidos por SHA-256 e
movimentações sobrepostas são deduplicadas por conta e identificador bancário.
Nenhum arquivo OFX é alterado.

## Fase 2: classificação assistida

```bash
python3 scripts/03_prepare_classification.py
python3 scripts/04_apply_classification.py
```

O primeiro comando agrupa contrapartes e cria uma fila de revisão ordenada pelo
maior lançamento individual. Decisões e exceções ficam em `data/knowledge/`.
Dúvidas adiadas recebem uma classificação explícita e uma fila de investigação
própria, sem bloquear as demais. O segundo comando somente produz a tabela
classificada quando todas as dimensões obrigatórias estiverem resolvidas. Consulte
[`docs/classification.md`](docs/classification.md) para o contrato completo.

## Testes

```bash
python3 -m pytest
python3 -m ruff check .
```
