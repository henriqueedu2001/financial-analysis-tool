# Classificação assistida

A classificação combina regras estruturais versionadas em
`config/base_classification_rules.csv` com decisões pessoais locais em
`data/knowledge/`. Nenhum conhecimento pessoal é enviado ao Git.

## Dimensões

* `nature`: papel financeiro da movimentação;
* `category` e `subcategory`: finalidade;
* `recurrence`: `fixed_contractual`, `variable_habitual`, `non_recurring` ou
  `not_applicable`;
* `flexibility`: `mandatory`, `flexible` ou `not_applicable`;
* `cost_treatment`: `recurring`, `expanded` ou `outside`;
* `peak_eligible`: indica se a movimentação pode participar da análise de picos.

## Precedência

Regras aplicáveis são mescladas por prioridade crescente. Campos preenchidos por
uma regra de prioridade maior substituem os anteriores. Uma exceção vinculada ao
`transaction_id` sempre prevalece.

As regras pessoais podem ter datas e limites de valor. Isso permite representar
uma mesma contraparte com valores ou significados diferentes ao longo do tempo.

Uma movimentação bancária que agrega finalidades diferentes pode ser decomposta
por `data/knowledge/transaction_allocations.csv`. As parcelas precisam somar
exatamente o valor original em centavos. A saída analítica preserva o identificador
e o valor originais para auditoria.

Linhas bancárias distintas que pertencem ao mesmo episódio podem ser ligadas em
`data/knowledge/transaction_events.csv`. Essa associação não soma nem altera os
lançamentos. Ela permite que análises posteriores de picos tratem o episódio como
uma unidade, preservando cada pagamento original.

Uma dúvida não precisa bloquear o fluxo. A transação pode receber natureza e
categoria explícitas de item não classificado e ser registrada em
`data/knowledge/investigation_queue.csv`. Itens marcados como `deprioritized`
permanecem desconhecidos por decisão do usuário. Itens `needs_investigation`
guardam qual evidência ainda poderia resolvê-los.

## Fluxo

```bash
python3 scripts/03_prepare_classification.py
python3 scripts/04_apply_classification.py
```

O primeiro comando produz grupos e uma fila de pendências. A fila é ordenada pelo
maior lançamento individual e depois pelo valor total do grupo. O segundo comando
se recusa a gerar a tabela final enquanto qualquer dimensão obrigatória estiver
vazia.
