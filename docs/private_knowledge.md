# Artefatos privados de conhecimento

As informações dadas por Henrique durante a revisão ficam em `data/knowledge/`,
que é integralmente ignorado pelo Git.

* `financial_facts.toml` registra definições globais e parâmetros da análise;
* `classification_rules.csv` registra decisões reutilizáveis por grupo e período;
* `transaction_overrides.csv` registra exceções individuais;
* `transaction_allocations.csv` decompõe uma movimentação com mais de uma
  finalidade sem alterar a linha bancária original;
* `transaction_events.csv` associa linhas bancárias distintas a uma mesma
  ocorrência analítica, por exemplo duas cobranças do mesmo episódio;
* `investigation_queue.csv` mantém dúvidas que podem ser resolvidas depois sem
  bloquear a classificação atual;
* `decision_log.md` preserva a justificativa humana em linguagem natural.

A fila de investigação diferencia `needs_investigation`, para casos que Henrique
quer esclarecer posteriormente, de `deprioritized`, para itens que devem continuar
como desconhecidos sem consumir tempo agora. Em ambos os casos a movimentação
recebe uma classificação explícita e não contamina métricas cuja natureza ainda
não foi determinada.

O código versionado contém apenas o contrato desses arquivos. Nenhum identificador
pessoal, contraparte, saldo ou classificação real deve aparecer em commits.
