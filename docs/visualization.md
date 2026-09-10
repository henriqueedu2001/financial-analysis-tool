# Contrato visual do relatório

Estas regras valem para todos os gráficos produzidos nas fases seguintes.

1. Toda série temporal usa pontos conectados por linhas (`lines+markers`). Barras
   não serão usadas para representar a passagem do tempo.
2. Os eixos têm títulos explícitos e unidades. Exemplos: `Data`, `Mês`,
   `Saldo (R$)` e `Despesa (R$)`.
3. Gráficos de pizza e rosca não serão usados. Composições por categoria usarão
   barras horizontais ordenadas, dot plots ou tabelas.
4. Datas ficam em ordem cronológica e dias sem movimento permanecem visíveis.
   Todos os eixos temporais exibem uma marca por mês.
5. Cor não será o único meio de distinguir séries. Rótulos, símbolos ou padrões
   complementarão a paleta com contraste adequado.
6. Séries relacionadas manterão cores consistentes em todo o relatório. Grades
   serão discretas e somente informação útil receberá destaque.
7. Não serão usados gráficos 3D. Eixos duplos serão evitados; quando duas escalas
   forem necessárias, serão usados painéis alinhados.
8. Cada gráfico informará período, unidade e definição relevante. Estimativas,
   cobertura parcial e meses incompletos serão identificados no próprio contexto.

O contrato segue a documentação oficial do Plotly para séries temporais, pontos e
títulos de eixos, e as orientações de acessibilidade do GOV.UK para não depender
apenas de cor e manter contraste. As referências estão registradas no README.
