# Reconstrução do cofrinho

## Escopo

O modelo usa apenas os aportes e resgates explicitamente encontrados no extrato
do Itaú. `APLICACAO COFRINHOS` aumenta a reserva e `RESGATE ... COFRINHOS`
reduz a reserva. O relatório usa o nome **deporte** para o segundo caso.

O saldo de R$ 26.000,00 em 31 de agosto de 2026 é a âncora conhecida de fim de
dia. O modelo reconstrói os dias anteriores de trás para frente e os posteriores
de frente para trás. Aportes posteriores que não aparecem nos extratos permanecem
fora do modelo, conforme decisão registrada em `financial_facts.toml`.

## Rendimentos

A referência pública é a série 12 do Sistema Gerenciador de Séries Temporais do
Banco Central, que fornece a taxa CDI em percentual ao dia. O arquivo versionado
`config/reference/cdi_daily.csv` permite reproduzir o resultado sem depender de
uma nova consulta à API.

Em cada data com taxa publicada, o rendimento estimado é aplicado sobre o saldo
de abertura. Aportes e deportes entram depois do rendimento daquele dia. Dias sem
taxa publicada recebem rendimento zero. O cálculo usa `Decimal`, arredondamento
monetário para centavos e 100% do CDI.

O modelo é deliberadamente simples. Não estima imposto de renda, IOF, tarifas,
carência ou diferenças específicas do produto do Itaú. A âncora corrige o nível
da série, mas não transforma movimentos ausentes em movimentos observados.

## Saídas

* `cofrinho_events.csv`: trilha auditável de cada aporte e deporte;
* `cofrinho_daily.csv`: saldo, juros e fluxos por dia;
* `cofrinho_monthly.csv`: aportes, deportes, juros e saldo por mês;
* `cofrinho_quality.csv`: reconciliação da âncora e controles do modelo.

Referências metodológicas: [SGS série 12 do Banco Central](https://www3.bcb.gov.br/sgspub/consultarmetadados/consultarMetadadosSeries.do?method=consultarMetadadosSeriesInternet&hdOidSerieSelecionada=12)
e [metodologia da Taxa DI da B3](https://b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-apuracao-da-taxa/).
