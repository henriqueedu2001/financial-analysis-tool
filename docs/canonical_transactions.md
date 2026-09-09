# Contrato da tabela canônica

`data/derived/transactions_canonical.csv` é a fonte normalizada para as fases
posteriores. O arquivo usa UTF-8, cabeçalho e uma movimentação por linha.

| Coluna | Significado |
| --- | --- |
| `transaction_id` | SHA-256 estável da identidade completa da movimentação |
| `account_id` | Nome local e não sensível da conta |
| `institution` | Instituição financeira |
| `account_fingerprint` | SHA-256 de `BANKID` e `ACCTID`; o número real não é exportado |
| `transaction_date` | Data contábil no formato `AAAA-MM-DD` |
| `amount_cents` | Valor exato em centavos; entradas positivas e saídas negativas |
| `transaction_type` | `TRNTYPE` original do OFX |
| `bank_transaction_id` | `FITID` original, quando presente |
| `description_raw` | Junção sem normalização de `NAME` e `MEMO` |
| `name_raw` | `NAME` original |
| `memo_raw` | `MEMO` original |
| `source_file` | Caminho relativo do OFX de origem |
| `source_sha256` | SHA-256 do conteúdo integral do OFX |
| `source_position` | Posição da movimentação dentro do arquivo |

`data/derived/statement_snapshots.csv` preserva os saldos declarados nos OFX,
sem repeti-los em todas as movimentações.

## Deduplicação

Arquivos com o mesmo SHA-256 são processados uma vez. A assinatura combina conta,
`FITID`, data, valor e descrição porque alguns bancos reutilizam `FITID`. Na ausência
dele, usa conta, data, valor, descrição e número da ocorrência. Conflitos de saldo
interrompem a execução.

Linhas sem `FITID` chamadas `Saldo do dia` ou `Saldo Anterior` são marcadores
artificiais presentes nos OFX do Banco do Brasil. Elas não representam fluxo
financeiro, ficam fora da tabela canônica e sua quantidade permanece registrada em
`source_inventory.csv`.
