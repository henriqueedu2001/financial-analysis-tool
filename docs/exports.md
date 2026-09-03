# Exportações

As exportações são geradas em memória e baixadas pelo navegador. Nenhum arquivo é
enviado automaticamente a serviços externos.

## Movimentações filtradas

CSV detalhado conforme período, contas, categorias e naturezas escolhidas. Inclui
descrição original, valor decimal exato, classificação atual e referências ao
arquivo, lote e linha de origem. Portanto, deve ser tratado como dado financeiro
pessoal.

## Resumo mensal

CSV com receitas, despesas, custo de vida, extraordinárias, poupança, taxa de
poupança, aporte líquido e patrimônio monitorado por mês.

## JSON analítico

Arquivo agregado voltado à análise textual externa. Ele não contém descrições
bancárias, nomes de arquivos nem identificadores de conta. Inclui totais do período,
burn rate, cobertura, série mensal e gastos por categoria.

Valores monetários são representados por strings decimais exatas:

```json
{
  "money_format": "decimal_string",
  "external_income": "6000.00",
  "savings_rate": "0.3583"
}
```

O uso de strings evita que a serialização JSON introduza aproximações binárias. Um
valor indisponível é `null`. Revise sempre o JSON antes de enviá-lo ao ChatGPT ou a
qualquer outro serviço.
