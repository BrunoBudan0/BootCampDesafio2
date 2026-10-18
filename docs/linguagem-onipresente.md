# Linguagem onipresente

Contexto: análise antifraude de Pix no banco do pagador. O motor recebe o Pix antes de o dinheiro sair, decide e grava o motivo. Saldo, liquidação e cadastro de clientes não fazem parte deste contexto.

Cada termo abaixo tem um significado só, e ele vale na conversa, nos documentos, nas tabelas e no código. Termo novo entra aqui antes de entrar no código. Se um termo mudar de sentido, o código muda junto.

## Regras de uso

1. Um termo, um significado. Se um termo começar a servir para duas coisas, ele vira dois termos.
2. Conversa em português, código em inglês. A coluna "No código" é a tradução oficial e não tem sinônimo.
3. O contrato da API manda nos nomes: o que é do pagador se chama `source` e o que é do recebedor se chama `destination`.
4. A tabela de regras do README usa os códigos de regra daqui.

## Palavras que não usamos

| Não diga | Diga | Por quê |
|---|---|---|
| score | pontuação de risco (da análise) ou credibilidade (do histórico) | No quadro, score aparecia nos dois sentidos, que são opostos |
| nota | pontos (de uma regra) ou pontuação de risco (da análise) | Mesmo motivo |
| perfil | política de risco (do banco) ou histórico do pagador | Eram duas coisas com o mesmo nome |
| usuário, cliente | pagador, recebedor ou banco cliente | Cliente pode ser o banco ou a pessoa |
| conta (sozinha) | conta de origem ou conta de destino | Um pagador pode ter várias contas |
| 2FA aprovado, 2FA reprovado | 2FA confirmado, 2FA recusado | Aprovado e reprovado são decisões do motor |
| Pix aprovado (para histórico) | Pix aceito | O histórico inclui o Pix que passou pelo 2FA |
| device novo, device conhecido | dispositivo não cadastrado, dispositivo cadastrado | Cadastrado é um fato gravado; novo depende de quem olha |
| validações cruciais, validações pontuais | regra eliminatória, regra regulatória, regra de pontuação | Não existe caminho mais curto para quem tem histórico: toda análise passa pelas mesmas etapas, e só uma regra eliminatória encerra antes |

## Fora do contexto

Existem no mundo do Pix, mas não neste sistema: liquidação, SPI, saldo, MED, bloqueio cautelar, chave Pix, DICT, cadastro de cliente. Se um deles aparecer numa discussão, estamos saindo do escopo.

## Quem participa

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Banco cliente | (a instalação) | Instituição que usa o motor. Cada banco tem a sua instalação e o seu banco de dados | Pagador |
| Pagador | `source` | Titular da conta de origem, identificado pelo documento | Banco cliente |
| Recebedor | `destination` | Titular da conta de destino, identificado pelo documento | |
| Conta de origem | `source_account` | Conta de onde sai o Pix: agência, número e data de abertura | Pagador |
| Conta de destino | `destination_account` | Conta para onde vai o Pix: participante, agência, número e data de abertura | Recebedor |
| Participante | `participant` | ISPB do banco do recebedor | Banco cliente |
| Documento | `document` | CPF (11 dígitos) ou CNPJ (14 caracteres, pode ter letras), guardado sem pontuação. É a identidade do histórico | Conta |
| Tipo de pessoa | `person_type`: `individual`, `company` | Sai do documento. MEI tem CNPJ e por isso é `company` | |

## O Pix e a análise

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Pix | `pix` | Pedido de transferência recebido em `POST /pix/transaction` | Transferência liquidada, que o motor não faz |
| Identificador do Pix | `pix_id` | O `id` do contrato. Um Pix tem uma análise só | Chave da análise |
| Análise | `pix_analysis` | Registro imutável do Pix recebido, das regras disparadas e da decisão | |
| Chave da análise | `analysis_key` | UUID da análise. É o `key` da resposta | Identificador do Pix |
| Data da transação | `transaction_date` | Data e hora do Pix, com o fuso que veio no pedido | Data de recebimento (`created_at`), que nenhuma regra usa |
| Horário local | `local_time` | A data da transação no fuso que veio nela. Decide o que é noite e o que é dia | Horário do servidor |
| Decisão | `decision` | `approved`, `two_factor_required` ou `rejected`. É do motor e nunca muda | Resultado do 2FA |
| Aprovado | `approved` | O Pix segue sem fricção | Pix aceito |
| 2FA solicitado | `two_factor_required` | O motor pede que o pagador confirme que é ele | |
| Reprovado | `rejected` | O Pix não sai | 2FA recusado |
| Confirmação de 2FA | `two_factor_confirmation` | Fato informado pelo banco cliente depois do 2FA: o resultado e a data | Decisão |
| 2FA confirmado | `confirmed` | O pagador provou que é ele | Aprovado |
| 2FA recusado | `denied` | O pagador não provou. Vira sinal de risco para os próximos Pix dele | Reprovado |
| Validade do 2FA | `two_factor_validity_minutes`, `two_factor_expires_at` | Prazo para a confirmação chegar, contado da data da transação | |
| 2FA pendente | (estado calculado) | 2FA solicitado, sem confirmação e dentro da validade. Na análise de um Pix novo, a validade é comparada com a data da transação desse Pix; no `GET`, com o relógio do servidor | |
| 2FA expirado | (estado calculado) | 2FA solicitado, sem confirmação e fora da validade. Não conta mais em nada | 2FA recusado |
| Pix aceito | `accepted_pix` | Pix aprovado direto ou com 2FA confirmado. Só ele forma o histórico do pagador | Aprovado |

## Histórico e janelas

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Histórico do pagador | `source_history` | Pix aceitos do documento do pagador dentro da janela de histórico | Tentativas |
| Tentativas | `attempts` | Todas as análises, com qualquer decisão. Usadas em rajada, fan-in e dispositivo compartilhado | Histórico do pagador |
| Consumo de limite | `limit_usage` | Pix aceitos mais 2FA pendentes. Usado nos limites regulatórios | |
| Janela | `window` | Período que termina na data da transação analisada. Nunca é contado a partir do relógio do servidor | |
| Janela de histórico | `history_window_days` | Quantos dias de Pix aceitos formam o histórico (90) | |
| Janela de curto prazo | `short_term_window_minutes` | Período curto em que os Pix do pagador são somados para enfrentar o fracionamento (24 h) | Janela de histórico |
| Valor acumulado | `short_term_amount` | O Pix analisado mais os Pix aceitos e 2FA pendentes do pagador na janela de curto prazo, no total ou só para o mesmo recebedor | Valor do Pix |
| Fracionamento | `split` | Dividir um valor em vários Pix menores para ficar abaixo de um limite. Toda regra de valor compara também o valor acumulado | Rajada |
| Limite noturno do pagador | `source_nightly_limit` | R$ 1.000 por padrão para PF. O aumento aprovado pelo banco vale 24 h depois do pedido; a redução vale na hora | Teto de conta nova |
| Início frio | `cold_start` | Pagador sem nenhum Pix aceito (n = 0) | Conta nova |
| Conta nova | `new_account` | Conta de origem aberta há menos de `new_account_age_days` dias (30) | Início frio: uma conta antiga pode estar em início frio |

## Regras, pontuação e credibilidade

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Regra | `rule` | Uma pergunta sobre o Pix com resultado definido. Tem código único | |
| Código da regra | `rule.code` | Nome da regra em inglês. Aparece no código, no `metadata` e no README | |
| Tipo de regra | `rule.kind` | `scoring`, `reducer`, `eliminatory` ou `regulatory` | Família |
| Regra de pontuação | `scoring` | Soma pontos na pontuação de risco | |
| Redutor | `reducer` | Tira pontos só da parte da pontuação que ele desmente: o aparelho cadastrado tira da identidade, o destino conhecido tira dos sinais da relação, e a mesma titularidade tira dos sinais da relação e do valor | |
| Regra eliminatória | `eliminatory` | Decide direto, sem passar pela pontuação. O banco pode editar | Regra regulatória |
| Regra regulatória | `regulatory` | Vem de norma do BCB. Os valores ficam fixos no código e o banco não edita | Regra eliminatória |
| Decisão forçada | `forced_decision` | A decisão que uma regra eliminatória ou regulatória impõe quando dispara | |
| Família | `rule.family` | Grupo das regras de pontuação: `identity` (identidade), `velocity` (tempo), `amount` (valor), `counterparty` (contraparte) | Tipo de regra |
| Teto da família | `*_family_cap` | Máximo de pontos que uma família soma numa análise. A contraparte tem teto alto (70) porque só a evidência da base pode chegar até ele | |
| Teto da relação | `counterparty_relationship_cap` | Máximo de pontos que os sinais da relação somam dentro da contraparte (30). Impede que relação somada a um único sinal da base reprove, como numa vaquinha para uma conta nova | Teto da família |
| Comportamento | (velocidade, valor e relação) | O que o próprio pagador está fazendo de diferente: conta nova, rajada, valor fora do padrão, destino novo, conta de destino recente. É atipicidade, não evidência | Evidência |
| Evidência | (identidade e base) | Dúvida sobre quem está pagando, ou o que a base inteira viu do recebedor. Só ela, uma regra eliminatória ou o limite noturno reprovam no modelo equilibrado | Comportamento |
| Teto do comportamento | `behavior_score_cap` | Máximo que velocidade, valor e relação somam juntos na pontuação de risco (65 no modelo equilibrado). Abaixo do limiar de reprovação, para comportamento atípico sozinho chegar no máximo ao 2FA | Teto da família |
| Regra disparada | `rule_hit` | Regra que deu positivo numa análise, com os pontos e o motivo | |
| Motivo | `reason` | Frase que explica o disparo com o valor observado | |
| Pontos | `points` | Quanto uma regra disparada soma ou tira | Pontuação de risco |
| Pontuação de risco | `risk_score` | Identidade, mais comportamento, mais a parte da base na contraparte. Cada família é limitada ao seu teto e perde os redutores que a desmentem, sem ficar abaixo de zero. Os sinais da relação têm o teto da relação; velocidade, valor e relação juntos têm o teto do comportamento | Credibilidade |
| Limiar de 2FA | `two_factor_score_threshold` | Pontuação a partir da qual o motor pede 2FA (40) | |
| Limiar de reprovação | `rejection_score_threshold` | Pontuação a partir da qual o motor reprova (70) | |
| Severidade | (ordem) | `rejected` > `two_factor_required` > `approved`. A decisão final é a mais severa entre a faixa da pontuação de risco e as decisões forçadas | |
| Credibilidade | `credibility_blend` | Quanto o histórico próprio pesa contra uma referência: n / (n + k) | Pontuação de risco |
| Peso da referência | `k` | Quantos casos próprios valem o mesmo que a referência (5 para o pagador, 30 para a população) | |
| Mediana do pagador | `source_median_amount` | Mediana dos Pix aceitos do pagador na janela de histórico com o mesmo par pagador → recebedor do Pix analisado (PF→PF, PF→PJ, PJ→PF ou PJ→PJ) | |
| Ticket médio de referência | `reference_average_ticket_*` | Ticket médio do Pix publicado pelo BCB para cada par pagador → recebedor (PF→PF R$ 268,64; PF→PJ R$ 112,42; PJ→PF R$ 549,58; PJ→PJ R$ 5.404,53). É uma média, não uma mediana | Mediana da população |
| Mediana da população | `population_median_amount` | Mediana dos Pix aceitos de todos os pagadores com o mesmo par pagador → recebedor, misturada com o ticket médio de referência pela credibilidade | Ticket médio de referência |
| Base de comparação | `baseline_amount` | (n × mediana do pagador + k × mediana da população) / (n + k) | |
| Valor fora do padrão | `amount_above_baseline` | Pix acima do multiplicador vezes a base de comparação (5 vezes) | Valor muito fora do padrão |
| Valor muito fora do padrão | `amount_far_above_baseline` | Pix acima de um multiplicador maior da base de comparação (20 vezes). Pesa mais e é exclusiva com a anterior: dispara só a mais grave | Valor fora do padrão |
| Piso das regras de valor | `amount_rules_floor_cents` | Abaixo dele, as regras da família valor não pontuam (R$ 100) | |
| Teto de conta nova | `new_account_cap_*` | Maior Pix que uma conta nova faz sem fricção (PF R$ 1.000, PJ R$ 10.000) | Limite regulatório |
| Teto habitual | `usual_ceiling_amount` | O maior entre a base de comparação e o maior Pix aceito do pagador na janela de histórico, sem contar Pix para conta própria nem os aceitos na janela de curto prazo | Teto de conta nova |
| Familiaridade | `familiarity` | Se aquele IP, local ou canal já apareceu nos Pix aceitos do pagador. Só o que nunca apareceu pontua, e pesa mais quanto maior o histórico do pagador | Dispositivo cadastrado |
| Local | `location` | Latitude e longitude arredondadas em 2 casas (cerca de 1 km) | |

## Contraparte

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Destino novo | `new_destination` | Recebedor cujo documento não aparece nos Pix aceitos do pagador anteriores à janela de curto prazo. Pix aceitos nas últimas 24 h ainda não tornam o destino conhecido, para que aquecer um destino no mesmo dia não funcione | Conta de destino recente |
| Destino conhecido | `known_destination` | Recebedor com pelo menos N Pix aceitos do pagador (3), contando só os anteriores à janela de curto prazo | |
| Conta de destino recente | `destination_account_opened_*` | Conta de destino aberta há poucos dias | Destino novo |
| Mesma titularidade | `same_owner` | Documento do pagador igual ao do recebedor | |
| Fan-in | `destination_receiving_from_many_sources` | Recebedor PF que recebe Pix a partir do piso das regras de valor de muitos pagadores diferentes em pouco tempo | |
| Recebedor com reprovações | `destination_rejected_for_other_sources` | Recebedor com 2FA recusados, ou com Pix reprovados em que disparou alguma regra de contraparte, vindos de outros pagadores em pouco tempo. Só soma risco e ignora as análises em que ela mesma disparou | |
| Recebedor em várias contas | `destination_document_in_many_accounts` | Mesmo documento de recebedor recebendo em várias contas de destino diferentes em pouco tempo. Recebedor PJ tem um limite próprio, bem maior | |
| Limite de PJ | `company_threshold` | Limite próprio de uma regra para pessoa jurídica: o recebedor PJ em `destination_document_in_many_accounts` e em `new_destination_above_usual_ceiling`, e o pagador PJ em `burst_of_pix`. O banco muda criando uma versão nova da política | |
| Alcance do sinal | `rule.counterparty_signal`: `relationship`, `base` | Diz se uma regra de contraparte depende só deste pagador ou de todos os pagadores da instalação | Família |
| Sinal da relação | `relationship` | Regra de contraparte que depende do que este pagador sabe do recebedor: idade da conta de destino e destino novo acima do teto habitual. Os redutores abatem | Sinal da base |
| Sinal da base | `base` | Regra de contraparte que depende do que todos os pagadores da instalação viram do recebedor: fan-in, recebedor com reprovações e recebedor em várias contas. Os redutores não abatem, porque o que um pagador sabe do recebedor não apaga o que a base inteira viu | Sinal da relação |
| Risco do recebedor | `destination_risk` | Pontos dos sinais da relação menos os redutores de mesma titularidade e destino conhecido, nunca abaixo de zero, mais os pontos dos sinais da base. Sem teto | Pontuação de risco |
| Alerta de recebedor | `destination_alert` | Aviso no `metadata` quando o risco do recebedor atinge o limiar. Não muda a decisão | 2FA |
| Limiar de alerta | `destination_alert_threshold` | Risco do recebedor a partir do qual sai o alerta (30) | |
| Conta laranja | (conceito) | Conta usada para receber e repassar dinheiro de fraude. É o que as regras de contraparte procuram | |

## Dispositivo e canal

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Dispositivo | `device_id` | Aparelho que iniciou o Pix | |
| Dispositivo cadastrado | `registered_device` | Aparelho que o motor já reconheceu para aquele pagador | Familiaridade |
| Origem do cadastro | `registration_origin`: `two_factor`, `first_seen` | 2FA confirmado naquele aparelho, ou primeiro Pix aceito do pagador | |
| Dispositivo não cadastrado | (estado calculado) | Aparelho sem cadastro para aquele pagador. Sujeito aos limites da Res. BCB 403: R$ 200 por Pix e R$ 1.000 por dia | |
| Dispositivo compartilhado | `device_used_by_many_sources` | Mesmo aparelho usado por muitos pagadores PF diferentes em pouco tempo. Empresas que pagam pelo mesmo computador, como um escritório de contabilidade, não contam | |
| Canal | `channel` | Por onde o Pix foi iniciado: `app`, `web` e outros que aparecerem. Texto aberto | Dispositivo |
| Viagem impossível | `impossible_travel` | Pix a mais de 50 km do último Pix aceito do pagador com geolocalização, num deslocamento que exigiria mais de 900 km/h | |
| Rajada | `burst_of_pix` | Muitos Pix do mesmo pagador em poucos minutos | |

## Política de risco

| Termo | No código | Definição | Não confundir com |
|---|---|---|---|
| Política de risco | `risk_policy` | Conjunto nomeado de parâmetros e ajustes de regra. É o apetite de risco do banco | Histórico do pagador |
| Modelo de política | `template` | Política pronta (conservadora, equilibrada, permissiva) usada como ponto de partida. Não muda | Política do banco |
| Política do banco | `bank` | A única política que decide as análises e a única que o banco edita | Modelo de política |
| Versão | `risk_policy_version` | Estado completo de uma política num momento. Editar cria uma versão nova e nunca altera a anterior | |
| Versão vigente | `current_version` | A versão mais recente da política do banco. É a que decide as análises novas | |
| Ajuste de regra | `risk_policy_rule_setting` | Para cada versão e cada regra editável: ligada ou não, pontos, limite e janela | Parâmetro da política |
| Parâmetro da política | colunas de `risk_policy_version` | Número que vale para várias regras: janela de histórico, pesos, tetos, limiares, validade do 2FA | Ajuste de regra |
| Motivo da mudança | `change_reason` | Por que a versão foi criada | Motivo |
| Parâmetro regulatório | constantes no código | Valor que vem de norma. Fica fora da política | Parâmetro da política |
| Política de referência | `balanced` | O modelo equilibrado, versão 1. É a régua da QI: define o que é recomendado e é contra ele que se mede o quanto o banco afrouxou | Política do banco |
| Afrouxar | (direção de um ajuste) | Mudar um parâmetro ou ajuste para o lado que deixa passar mais Pix: subir um limiar ou um multiplicador, baixar pontos ou tetos, desligar uma regra de pontuação. Ficar mais rígido nunca é afrouxar | |
| Faixa de segurança | `risk_policy_guardrail` | Para cada ajuste que muda se uma regra dispara (multiplicador, piso, contagem), o limite além do qual o banco não pode afrouxar | Caso-âncora |
| Zona de atenção | (estado calculado) | Edição que afrouxa algum ajuste em relação à política de referência, sem passar da faixa de segurança. É aceita só com o aceite do risco | |
| Aceite do risco | `risk_acknowledged`, `requested_by` | Confirmação gravada na versão de que o banco afrouxou a política sabendo do risco, com a identificação de quem pediu | Motivo da mudança |
| Caso-âncora | `anchor_case` | Perfil de fraude conhecido (as regras que ele dispara) recalculado com a política proposta. Se a política deixar de dar a decisão mínima para ele, a edição é recusada | Faixa de segurança |
