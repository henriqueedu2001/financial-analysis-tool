# Relatório final

O relatório é gerado a partir de `config/report_template.tex`. O script
`scripts/10_build_report.py` injeta somente resultados calculados, referências aos
oito gráficos e verificações de qualidade. A fonte preenchida e o PDF contêm
informações pessoais e, por isso, são gravados em `output/`, ignorado pelo Git.

## Execução local

O compilador é o Tectonic. O script procura, nesta ordem, `--tectonic`, a variável
`TECTONIC_BIN`, o executável no `PATH` e a instalação local usada pelo projeto
`~/Projects/flike-tcc`.

```bash
python3 scripts/10_build_report.py
```

Saídas:

* `output/latex/analise_financeira_pessoal.tex`;
* `output/pdf/analise_financeira_pessoal.pdf`;
* logs e intermediários em `output/latex/build/`.

O relatório diferencia fatos observados de estimativas, explicita meses
comparáveis, preserva desconhecidos e não converte transferências próprias em
receita ou despesa.

## Execução completa com Docker

Na raiz do repositório:

```bash
docker compose run --rm --build analysis
```

O contêiner lê os extratos e o conhecimento privado pelo volume `data/`, gera
todos os artefatos intermediários e publica o PDF no volume `output/`. O código e
a imagem não incorporam os extratos. A primeira execução precisa de acesso à
internet para baixar o conjunto de pacotes LaTeX usado pelo Tectonic; esse cache
é persistido no volume `tectonic-cache`.
