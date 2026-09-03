# Contrato do CSV canônico — versão 1

O arquivo deve ser CSV UTF-8, conter uma linha de cabeçalho e usar vírgula como
separador. Cada linha representa uma movimentação. O importador da Fase 2 fará a
validação integral antes de qualquer confirmação.

## Colunas

| Coluna | Obrigatória | Formato e regra |
|---|---:|---|
| `transaction_date` | sim | Data ISO `AAAA-MM-DD` |
| `account` | sim | Nome exato de uma conta cadastrada |
| `description` | sim | Texto bancário original, sem normalização destrutiva |
| `amount` | sim | Decimal com ponto, no máximo 2 casas; entrada positiva e saída negativa |
| `balance_after` | não | Decimal com ponto, no máximo 2 casas |
| `nature` | sim | Um dos valores listados abaixo |
| `category` | não | Categoria existente ou `A revisar` |
| `subcategory` | não | Subcategoria existente ou `A revisar` |
| `is_internal_transfer` | sim | `true` ou `false` |
| `is_extraordinary` | sim | `true` ou `false` |
| `source_file` | sim | Nome do arquivo bancário que originou a linha |
| `source_row` | sim | Número ou identificador estável da linha de origem |
| `confidence` | não | Decimal entre `0` e `1` |

Valores aceitos em `nature`:

- `income`
- `expense`
- `transfer`
- `investment_return`
- `refund`
- `fee`
- `adjustment`
- `unclassified`

## Convenções

- Campos vazios continuam presentes entre separadores, como em `,,`.
- Valores monetários não usam símbolo, separador de milhar nem vírgula decimal.
- `description`, data e valor são preservados na tabela bruta exatamente como
  importados. A representação normalizada usa centavos inteiros.
- O nome do CSV enviado ao aplicativo não substitui `source_file`: o primeiro
  identifica o lote recebido e o segundo mantém a rastreabilidade declarada pela
  ferramenta que gerou o CSV.
- Linhas inválidas serão exibidas na prévia e não serão importadas silenciosamente.
- Colunas desconhecidas serão preservadas no payload bruto para auditoria, mesmo
  que não participem do modelo normalizado.
- Um lote CSV contém exatamente uma conta. Arquivos consolidados devem ser
  separados por conta antes da importação para preservar a fronteira de auditoria.

## Exemplo mínimo

```csv
transaction_date,account,description,amount,balance_after,nature,category,subcategory,is_internal_transfer,is_extraordinary,source_file,source_row,confidence
2026-01-05,Conta Fluxo,SALARIO EMPRESA EXEMPLO,6000.00,7500.00,income,Receitas,Salário,false,false,extrato_fluxo_ficticio.pdf,2,0.99
```
