# Métricas mensais e picos de gasto

## Períodos e cobertura

O sistema produz uma linha para cada mês entre janeiro de 2025 e o último dia
observado. O último mês é incompleto quando os dados terminam antes do seu fim.
Antes de janeiro de 2026, o consolidado contém somente o Banco do Brasil porque o
extrato disponível do Itaú começa em 2026. A coluna `account_coverage` impede que
esses períodos sejam confundidos com meses de cobertura integral.

As estatísticas principais de custo de vida usam apenas meses completos com todas
as contas disponíveis. Valores do mês incompleto continuam visíveis, mas não
entram nas médias nem no índice de sobrevivência.

## Definições

* Receita externa: salário, freela e ajuda familiar.
* Despesa externa bruta: consumo, despesas da empresa e tarifas.
* Despesa externa líquida: despesa bruta menos estornos e reembolsos. O resultado
  pode ser negativo quando os reembolsos superam os gastos do mês.
* Poupança: receita externa menos despesa externa líquida.
* Custo de vida recorrente: despesas marcadas com `cost_treatment=recurring`.
* Custo de vida ampliado: custo recorrente mais despesas atípicas marcadas como
  `expanded`.
* Aporte líquido: aportes menos deportes.
* Índice de sobrevivência: saldo do cofrinho no fim do mês dividido pelo custo de
  vida recorrente do mesmo mês.

Transações não classificadas permanecem em colunas próprias e não são inseridas
silenciosamente em receita, despesa ou custo de vida.

## Modelo de picos

O universo contém saídas marcadas como elegíveis para pico cuja recorrência é
`non_recurring` ou ainda desconhecida (`not_applicable`). Gastos contratuais e
hábitos recorrentes não participam, mesmo quando têm valor alto. Transações
ligadas ao mesmo evento são somadas; um reembolso integral neutraliza o episódio.

Para cada episódio, o modelo calcula o escore Z modificado unilateral:

```text
M = 0,6745 × (valor − mediana) / MAD
```

`MAD` é a mediana dos desvios absolutos em relação à mediana. Um episódio é pico
quando `M > 3,5`. A mediana e o MAD são resistentes aos próprios valores extremos,
e o teste unilateral procura apenas gastos anormalmente grandes. A recomendação
do limiar 3,5 vem do manual de análise exploratória do NIST. A documentação do
SciPy também descreve o MAD como uma medida mais robusta que o desvio padrão.

O resultado é descritivo, não causal. Um pico desconhecido continua identificado
como desconhecido; o modelo não inventa sua finalidade.

Referências:

* [NIST: detecção de outliers e escore Z modificado](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm)
* [SciPy: median absolute deviation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html)

## Saídas

* `monthly_metrics.csv`: métricas financeiras por mês;
* `monthly_category_spending.csv`: gastos por categoria e subcategoria;
* `metrics_summary.csv`: síntese do custo de vida e sobrevivência;
* `spending_peak_candidates.csv`: população, escore e decisão de cada episódio;
* `spending_peaks_monthly.csv`: frequência e valores dos picos por mês;
* `spending_peaks_summary.csv`: estatísticas gerais dos picos;
* `metrics_quality.csv`: reconciliações determinísticas.
