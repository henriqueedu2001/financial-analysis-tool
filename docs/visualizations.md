# Gráficos estáticos

## Execução

```bash
python3 scripts/09_build_visualizations.py
```

O script lê somente tabelas calculadas pelas fases anteriores. Ele não altera
extratos, classificações ou métricas. As figuras e o manifesto ficam em
`data/reports/figures/`, diretório privado ignorado pelo Git.

## Figuras

1. `01_saldos_diarios.png`: contas correntes, cofrinho estimado e total
   monitorado;
2. `02_receitas_gastos_diarios.png`: receitas, despesas e resultado diário;
3. `03_resultado_mensal.png`: receitas, despesas e poupança mensal;
4. `04_custo_de_vida_mensal.png`: custo recorrente, custo com atípicos e despesa
   bruta;
5. `05_cofrinho.png`: saldo reconstruído, aportes, deportes e aporte líquido;
6. `06_indice_sobrevivencia.png`: meses cobertos pela reserva;
7. `07_gastos_por_categoria.png`: ranking dos meses completos com todas as
   contas;
8. `08_picos_de_gasto.png`: picos individuais, frequência e magnitude mensal.

`manifest.json` registra título, descrição, período e tabelas de origem de cada
figura. Isso permite conferir quais dados sustentam cada visualização.

## Convenções

Séries temporais usam linhas e marcadores. Barras são usadas somente no ranking
por categoria. Todos os eixos informam variável e unidade. Símbolos e padrões
complementam as cores. Marcadores abertos identificam meses incompletos nos
gráficos mensais. Todos os eixos temporais têm ticks mensais. O saldo do cofrinho
permanece rotulado como estimado.

No gráfico diário, despesas aparecem abaixo de zero. `Fluxo líquido externo`
representa receitas externas menos despesas externas no dia e não é um saldo
acumulado.

Valores continuam armazenados em centavos inteiros nas tabelas. A conversão para
reais ocorre apenas na apresentação gráfica.

## Referências visuais

As escolhas seguem a documentação oficial do
[Plotly para linhas](https://plotly.com/python/line-charts/),
[configuração de eixos](https://plotly.com/python/axes/) e
[exportação estática](https://plotly.com/python/static-image-export/). As regras
de contraste, rotulagem e uso de meios além de cor seguem os
[princípios de visualização do GOV.UK](https://brand.design-system.service.gov.uk/data/)
e o
[guia de visualização acessível](https://www.gov.uk/government/publications/a-bite-sized-guide-to-visualising-data-a-dstl-biscuit-book/a-bite-sized-guide-to-visualising-data).

## Limitações

O gráfico diário preserva todos os dias e, por isso, períodos longos ficam
visualmente densos. O cofrinho só existe no intervalo reconstruído na Fase 4. O
ranking por categoria usa meses completos com cobertura de todas as contas para
evitar comparar períodos com bases diferentes.
