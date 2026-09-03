# Classificação e correções manuais

## Categorias

Categorias são hierárquicas e editáveis. As propriedades `is_living_cost`,
`is_essential`, `is_recurring` e `is_extraordinary_default` são padrões da
categoria. Desativar é preferível a excluir: movimentações históricas continuam
apontando para a mesma categoria e o slug permanece estável mesmo após renomeá-la.

Uma movimentação pode definir overrides individuais de custo de vida e
essencialidade. `null` significa “herdar da categoria”; `true` ou `false` registra
uma decisão explícita para aquela movimentação.

## Regras

Regras locais podem verificar:

- descrição contém texto;
- descrição corresponde a expressão regular;
- contraparte contém texto.

Menor número significa maior prioridade. Apenas a primeira regra ativa compatível
é aplicada. A regra pode alterar categoria, natureza e/ou indicação de despesa
extraordinária. Regex inválida e regra sem ação são rejeitadas.

As regras são aplicadas durante importações futuras. Elas não reclassificam o
histórico silenciosamente.

## Precedência manual e auditoria

Ao salvar uma correção na página **Movimentações**:

1. a origem da classificação passa a ser `manual`;
2. `manual_classification_locked` passa a ser verdadeiro;
3. uma entrada append-only é criada em `transaction_edits`, com valores anteriores
   e novos e um motivo opcional;
4. qualquer execução automática posterior ignora a movimentação bloqueada.

A linha bancária em `raw_transactions` nunca é alterada ou excluída. Assim, a
origem, o estado normalizado atual e o histórico de correções permanecem distintos.
