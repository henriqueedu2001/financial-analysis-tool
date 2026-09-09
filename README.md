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

## Fase 3: datas, saldos e séries diárias

```bash
python3 scripts/05_build_daily_series.py
```

O comando gera quatro tabelas reproduzíveis em `data/derived/`:

* `transactions_dated.csv`, com data contábil e data efetiva preservadas;
* `daily_balances.csv`, com saldo contábil e saldo analítico diário;
* `daily_flows.csv`, com receitas, despesas e demais fluxos por dia;
* `data_quality.csv`, com a origem das datas e reconciliação dos saldos.

O Banco do Brasil exige tratamento explícito do Rende Fácil. O saldo contábil e
a estimativa de liquidez operacional ficam em colunas distintas. Consulte
[`docs/dates_balances.md`](docs/dates_balances.md) para as definições e limitações.

O contrato dos gráficos futuros está em
[`docs/visualization.md`](docs/visualization.md). Ele determina pontos conectados
por linhas para séries temporais, eixos nomeados e a proibição de gráficos de
pizza. As escolhas se apoiam nas documentações do
[Plotly para linhas e pontos](https://plotly.com/python/line-charts/),
[Plotly para eixos](https://plotly.com/python/axes/) e
[GOV.UK para acessibilidade em gráficos](https://brand.design-system.service.gov.uk/data/).

## Testes

```bash
python3 -m pytest
python3 -m ruff check .
```
