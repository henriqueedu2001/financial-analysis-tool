# Definições das métricas

Todos os cálculos usam centavos inteiros e `Decimal`. Conversões para `float`
ocorrem somente na camada de visualização do Plotly.

- **Receitas externas:** entradas positivas que não são transferências internas nem
  ajustes.
- **Despesas externas:** valor absoluto das saídas que não são transferências
  internas nem ajustes.
- **Poupança gerada:** receitas externas menos despesas externas. Inclui o dinheiro
  que permaneceu na conta operacional.
- **Taxa de poupança:** poupança dividida por receitas externas. Sem receita, o
  resultado é indisponível.
- **Aporte líquido na reserva:** soma algébrica das transferências internas na conta
  marcada como reserva. Não é sinônimo de poupança.
- **Custo de vida observado:** despesas externas cuja categoria pertence ao custo
  de vida, respeitando o override da movimentação.
- **Burn rate normalizado:** média mensal do custo de vida em janela de 3, 6 ou 12
  meses. Despesas extraordinárias podem ser incluídas ou excluídas. Sem histórico
  cobrindo a janela, o resultado é indisponível.
- **Saldo reconstruído:** snapshot mais recente até a data mais a soma das
  movimentações posteriores ao snapshot.
- **Patrimônio monitorado:** soma dos saldos reconstruídos de todas as contas ativas
  incluídas no consolidado. Se uma delas não tiver saldo reconstruível, o total é
  indisponível em vez de apresentar um valor parcial.
- **Cobertura da reserva:** saldo reconstruído das contas de reserva elegíveis
  dividido pelo burn rate. Burn rate zero ou base insuficiente gera resultado
  indisponível.

As transferências alteram os saldos individuais, mas suas duas pontas somam zero no
patrimônio consolidado e não entram em receitas ou despesas externas.
