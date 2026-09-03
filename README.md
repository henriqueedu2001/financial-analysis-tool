# Ferramenta local de análise financeira pessoal

Aplicação local, de usuário único, para importar extratos convertidos em um CSV
canônico, revisar movimentações e calcular análises financeiras determinísticas.
Nenhuma integração bancária ou chamada a modelos de IA faz parte do MVP.

> Estado atual: **Fase 4 — Transferências e reconciliação**. Fundação, importação,
> consulta, correções, regras, transferências reversíveis e snapshots estão
> implementados. Métricas e exportação permanecem como próximas fases.

## Privacidade e dados

O banco SQLite e todos os arquivos colocados em `data/` são ignorados pelo Git.
Somente os arquivos `.gitkeep` que preservam a estrutura de pastas são versionados.
Não coloque senhas, tokens, números completos de cartão ou credenciais bancárias no
projeto. O arquivo de exemplo contém apenas dados fictícios.

Os extratos recebidos ficam separados por instituição, tipo de conta e ano em
`data/inbox/`. Consulte [`docs/data_storage.md`](docs/data_storage.md) para o ciclo
de vida completo. O número da conta lido do OFX não é salvo no SQLite: somente um
hash usado para impedir a mistura acidental de contas ou bancos.

## Requisitos no Ubuntu

- Python 3.11 ou mais recente
- `venv` e `pip`

Instalação para desenvolvimento:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Executar

```bash
source .venv/bin/activate
streamlit run app.py
```

Na primeira execução, a aplicação cria `data/finance.sqlite`, todas as tabelas e a
taxonomia inicial. Cadastre as contas em **Contas** e abra **Importação**. É possível
selecionar um arquivo já organizado em `data/inbox/` ou enviar um OFX/CSV. Para usar
outro banco em testes ou desenvolvimento, defina uma URL SQLAlchemy em
`FINANCE_DATABASE_URL`.

## Testar e verificar

```bash
source .venv/bin/activate
pytest
ruff check .
```

## Fundação arquitetural

- Valores monetários persistidos usam **centavos inteiros**. A camada de conversão
  rejeita `float` e aceita somente `Decimal`, texto decimal ou inteiro.
- `raw_transactions` preserva a linha recebida e sua representação textual;
  correções posteriores ficam em `transactions`.
- Cada movimentação normalizada aponta para a conta, o lote e a linha bruta.
- `classification_source` e `manual_classification_locked` permitem que uma
  correção manual prevaleça sobre regras futuras.
- Transferências são associações reversíveis entre duas movimentações originais;
  elas não serão fundidas ou removidas.
- Tipo técnico (`checking`, `savings` etc.) e papel financeiro (`operational`,
  `reserve`, `investment`, `liability`) são atributos distintos da conta.
- Confianças são persistidas em pontos-base inteiros (`0` a `10000`), evitando
  ponto flutuante também nesse campo.
- OFX 2/XML e OFX 1/SGML são aceitos. Linhas inválidas permanecem auditáveis e uma
  importação parcial exige confirmação explícita.
- Reimportações usam SHA-256 do conteúdo, não o nome do arquivo. Transações apenas
  parecidas são sinalizadas e nunca apagadas automaticamente.
- Cada correção manual gera um registro append-only em `transaction_edits` e
  bloqueia reclassificações automáticas futuras naquela movimentação.
- Regras locais são determinísticas, têm prioridade explícita e são aplicadas
  somente a novas importações. Consulte
  [`docs/classification.md`](docs/classification.md).
- Sugestões de transferência nunca confirmam pares automaticamente; ambiguidades
  exigem escolha manual. Consulte
  [`docs/transfers_reconciliation.md`](docs/transfers_reconciliation.md).

As tabelas criadas são `accounts`, `import_batches`, `raw_transactions`,
`transactions`, `transaction_edits`, `categories`, `classification_rules`,
`transfer_matches` e `balance_snapshots`.

## CSV canônico

O contrato formal está em [`docs/canonical_csv.md`](docs/canonical_csv.md). Um
arquivo inteiramente fictício está em
[`examples/canonical_statement_example.csv`](examples/canonical_statement_example.csv).

Resumo das colunas da versão 1:

```text
transaction_date, account, description, amount, balance_after, nature,
category, subcategory, is_internal_transfer, is_extraordinary,
source_file, source_row, confidence
```

Datas usam `AAAA-MM-DD`, booleanos usam `true`/`false` e valores monetários usam
ponto decimal, sem separador de milhar.

## Estrutura

```text
app.py                       entrada Streamlit
pages/                       páginas do MVP por domínio
finance/db/                  engine, sessão, criação e seed do banco
finance/models/              modelos e enums SQLAlchemy
finance/importers/           parsers, hashes e pré-visualização
finance/repositories/        confirmação transacional e contas
finance/money.py             conversão monetária exata
config/default_categories.yaml
docs/canonical_csv.md
examples/canonical_statement_example.csv
tests/
data/                        dados pessoais locais ignorados pelo Git
```

## Escopo incremental

1. **Fundação (concluída):** estrutura, modelos, banco, categorias, contrato CSV,
   interface inicial e testes de infraestrutura/dinheiro.
2. **Importação (concluída):** parser Pydantic para CSV, OFX XML/SGML, prévia,
   validação, reconciliação inicial, hashes, deduplicação, lotes e auditoria.
3. **Movimentações e categorias (concluída):** consulta, filtros, edição auditável,
   CRUD por desativação e regras com precedência manual.
4. **Transferências e reconciliação (concluída):** sugestões ambíguas e
   reversíveis, associação manual, snapshots e tratamento explícito de
   divergências.
5. **Métricas e dashboard:** métricas financeiras testadas, séries mensais e
   gráficos Plotly.
6. **Exportação:** CSV filtrado, resumo mensal e JSON analítico.
7. **Empacotamento:** Docker Compose opcional para iniciar a aplicação com um único
   comando, mantendo SQLite e extratos em volume local e fora da imagem.

## Limitações atuais

Um OFX sem saldo inicial oferece apenas um snapshot final, portanto não produz uma
reconciliação independente até existir outro saldo conhecido. A sugestão de
transferências exige valores absolutos iguais; tarifas bancárias separadas continuam
como movimentações próprias. XLS e PDF são preservados na inbox, mas não são
formatos de importação. Migrações de schema ainda não são necessárias antes do
primeiro banco pessoal; Alembic será avaliado antes de alterações futuras de schema.
