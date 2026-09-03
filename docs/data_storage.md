# Armazenamento local dos extratos

Todos os caminhos abaixo ficam dentro de `data/` e são ignorados pelo Git.

```text
data/
├── inbox/<instituição>/<tipo_de_conta>/<ano>/
├── raw/<instituição>/account_<id>/<ano>/
├── processed/
├── rejected/
└── finance.sqlite
```

## Ciclo de vida

1. **`inbox/`** recebe arquivos baixados do banco que ainda não foram confirmados.
   Instituição, tipo da conta e ano são separados no caminho. O nome original do
   arquivo é preservado.
2. A página **Importação** lê OFX ou CSV da inbox e produz uma prévia sem alterar o
   histórico.
3. Na confirmação, o conteúdo é copiado para **`raw/`** com um prefixo derivado de
   SHA-256. O arquivo original nunca é sobrescrito silenciosamente.
4. O SQLite registra o hash integral, o nome recebido, o caminho arquivado, a conta
   local, os totais, a validação e cada linha bruta.
5. **`processed/`** e **`rejected/`** ficam reservados para artefatos derivados e
   arquivos totalmente rejeitados. Linhas isoladas inválidas são mantidas no lote
   como evidência bruta, sem criar uma movimentação normalizada.

O número completo da conta OFX não é gravado no SQLite. O sistema calcula um hash
com instituição, agência e conta. Depois da primeira confirmação, esse hash fica
vinculado à conta local e impede que um OFX de outra conta ou banco seja misturado
por engano.
