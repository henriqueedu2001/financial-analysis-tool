# Transferências internas e reconciliação

## Sugestões de transferência

O sistema compara movimentações com:

- valores absolutos iguais;
- sinais opostos;
- contas diferentes;
- datas separadas por no máximo três dias;
- similaridade entre descrições, usada apenas para compor a confiança.

Uma sugestão nunca altera as movimentações. Se uma saída ou entrada possuir mais de
uma contraparte possível, todas são marcadas como ambíguas e a interface exige uma
confirmação adicional. Isso cobre valores repetidos e transferências na virada do
mês sem pareamento silencioso.

Ao confirmar, as duas movimentações continuam existindo, passam a ter natureza
`transfer` e são ligadas por `transfer_matches`. Desassociar muda o vínculo para
`rejected` em vez de apagá-lo e restaura a natureza de entrada/saída conforme o
sinal. Uma ponta sem contraparte no histórico também pode ser marcada manualmente.

## Reconciliação

`balance_snapshots` guarda um saldo conhecido para uma conta e data. Saldos finais
presentes em importações confirmadas geram snapshots automaticamente; o usuário
também pode registrar um saldo manual.

Entre dois snapshots da mesma conta:

```text
saldo calculado = saldo inicial + soma das movimentações após o início e até o fim
diferença = saldo calculado - saldo final informado
```

Uma diferença diferente de zero permanece visível. Dois saldos conflitantes para a
mesma conta e data são rejeitados. Um OFX que fornece apenas saldo final cria um
snapshot, mas precisa de outro snapshot para uma reconciliação independente.
