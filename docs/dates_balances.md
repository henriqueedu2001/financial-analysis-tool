# Datas, saldos e fluxos diários

## Duas datas, duas funções

`transaction_date` continua imutável e representa a data contábil (`DTPOSTED`) do
OFX. A tabela `transactions_dated.csv` acrescenta:

* `posting_date`: cópia explícita da data contábil;
* `operation_date`: data indicada na descrição bancária, quando ela está entre
  zero e quatro dias antes da data contábil;
* `operation_date_source`: origem da escolha;
* `operation_posting_lag_days`: diferença inteira entre as duas datas.

O limite de quatro dias cobre fins de semana e feriados observados nos arquivos.
Datas impossíveis, posteriores ao lançamento ou mais antigas usam a data contábil.
Os fluxos analíticos usam `operation_date`. A reconstrução do saldo bancário usa
`posting_date`, pois os saldos-âncora do OFX pertencem ao calendário contábil.

## Saldo diário

O saldo contábil é reconstruído de trás para frente a partir do último saldo
informado pelo banco. Todos os dias corridos aparecem, inclusive os sem
movimentação.

No Banco do Brasil, o Rende Fácil aparece como transferências automáticas que
frequentemente zeram a conta corrente. Por isso `daily_balances.csv` preserva:

* `ledger_balance_cents`: saldo contábil exato;
* `liquidity_adjustment_cents`: principal acumulado inferido das transferências do
  Rende Fácil, com ponto inicial igual a zero;
* `analysis_balance_cents`: soma dos dois anteriores.

O saldo analítico do Banco do Brasil é uma aproximação de liquidez, não inclui o
saldo anterior ao primeiro extrato nem rendimentos acumulados. Para o Itaú, o
saldo analítico é igual ao saldo contábil. O consolidado anterior a 2 de janeiro
de 2026 tem cobertura parcial porque o extrato do Itaú começa nessa data; a coluna
`coverage_complete` registra essa diferença.

## Fluxos diários

`daily_flows.csv` separa entradas e saídas bancárias dos conceitos analíticos.
Receitas externas incluem salário, freela e ajuda familiar. Despesas externas
incluem consumo, despesas da empresa e tarifas. Aportes, deportes, rendimentos,
estornos, transferências e valores não classificados permanecem em colunas
próprias e não são silenciosamente tratados como receita ou despesa.

Uma conta só recebe linhas dentro do período em que há dados seus. O consolidado
continua por todo o período disponível, mas `coverage_complete=false` identifica
os dias em que nem todas as contas estão cobertas.

Todos os valores monetários permanecem em centavos inteiros.
