# Modelagem de dados

Os termos seguem a [linguagem onipresente](linguagem-onipresente.md).

## Visão geral

```
decision 1-N rule                     (decisão forçada das eliminatórias e regulatórias)
decision 1-N pix_analysis

risk_policy 1-N risk_policy_version 1-N risk_policy_rule_setting N-1 rule
                        |
                        1-N pix_analysis 1-N pix_analysis_rule_hit N-1 rule
                                 |
                                 1-0..1 two_factor_confirmation
                                 1-N    registered_device          (a análise que originou o cadastro)

source_nightly_limit                                               (limite noturno aprovado, por pagador)

VIEW accepted_pix = pix_analysis aprovadas + pix_analysis com 2FA confirmado
```

## Princípios

1. **Só INSERT.** Uma função de gatilho comum recusa UPDATE e DELETE em todas as tabelas. A decisão do motor nunca muda; o 2FA é um fato novo; editar a política cria uma versão nova.
2. **Um Pix, uma análise.** `pix_id` é UNIQUE. O mesmo id com o mesmo conteúdo devolve a análise gravada; o mesmo id com outro conteúdo é recusado.
3. **Janelas pela data da transação.** Toda janela termina no `transaction_date` do Pix analisado. Nenhuma regra lê `now()` nem `created_at`. Exceção consciente: o `GET` calcula se um 2FA está pendente ou expirado com o relógio do servidor, porque isso é apresentação, não regra.
4. **Travas por pagador, aparelho e recebedor.** A análise começa com `pg_advisory_xact_lock` no documento do pagador, no `device_id` e no documento do recebedor, sempre na mesma ordem (pelo valor numérico da chave) para não haver deadlock. Pix simultâneos do mesmo pagador, do mesmo aparelho ou para o mesmo recebedor enxergam uns aos outros, o que fecha a rajada, o limite, a fazenda de aparelhos e o fan-in feitos em paralelo. A confirmação de 2FA pega a trava do pagador.
5. **Um COMMIT por fato.** Análise, regras disparadas e cadastro `first_seen` entram juntos. Confirmação de 2FA e cadastro `two_factor` entram juntos. Versão da política e todos os seus ajustes de regra entram juntos.
6. **Nenhum id do banco sai da API.** Para fora vão `analysis_key` (UUID), `pix_id`, nome da política e número da versão.
7. **Dinheiro em centavos** (BIGINT).
8. **Nada se burla fracionando.** Toda regra que compara um valor com um limite compara o maior entre o Pix analisado e o valor acumulado de curto prazo: o Pix analisado mais os Pix aceitos e 2FA pendentes do mesmo pagador dentro de `short_term_window_minutes`. Cada regra diz qual acumulado usa: o total do pagador ou só o que foi para o mesmo recebedor. Dois Pix de R$ 1.000 contam como R$ 2.000.
9. **O banco guarda a estrutura; a aplicação valida os valores.** O banco garante o que só ele consegue garantir: chaves, NOT NULL, UNIQUE (que segura idempotência e concorrência), a política do banco única e o Só INSERT. CHECK de domínio fica só nas tabelas semeadas (`rule`, `risk_policy`, `risk_policy_guardrail`), que nenhuma rota escreve e que por isso só o banco pode conferir. Nas tabelas que a API escreve, cada valor é validado no schema JSON (400) ou no controller (422) antes do INSERT; a seção "Garantido pelo código, não pelo banco" diz onde fica cada regra.

## Tabelas

### decision

Tabela de domínio, no padrão `sample_entity_status` do Base Service.

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | SERIAL | PK |
| `enumerator` | VARCHAR(30) | UNIQUE. Valores: `approved`, `two_factor_required`, `rejected` |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

### rule

Catálogo de regras, semeado. Diz o que cada regra é e qual a forma dos seus ajustes.

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | SERIAL | PK |
| `name` | VARCHAR(80) | UNIQUE. Nome da regra em inglês, como `burst_of_pix`. Sai na API como `code` |
| `kind` | VARCHAR(20) | CHECK em `scoring`, `reducer`, `eliminatory`, `regulatory` |
| `family` | VARCHAR(20) NULL | CHECK em `identity`, `velocity`, `amount`, `counterparty`. Preenchida se e somente se `kind = 'scoring'` |
| `counterparty_signal` | VARCHAR(15) NULL | CHECK em `relationship`, `base`. Preenchida se e somente se `family = 'counterparty'` |
| `forced_decision_id` | INTEGER NULL | FK `decision`. Preenchida se e somente se `kind` for `eliminatory` ou `regulatory` |
| `threshold_unit` | VARCHAR(30) NULL | CHECK em `count`, `days`, `km_per_hour`, `multiplier`, `credibility_weight`. Nula quando a regra não tem limite |
| `uses_window_minutes` | BOOLEAN | A regra tem janela própria em minutos |
| `uses_company_threshold` | BOOLEAN | A regra tem limite próprio para recebedor PJ (`company_threshold`) |
| `description` | VARCHAR(255) | Frase em português que vai para o README |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

### risk_policy

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | SERIAL | PK |
| `name` | VARCHAR(50) | UNIQUE |
| `kind` | VARCHAR(10) | CHECK em `template`, `bank` |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

Índice único parcial em `kind` onde `kind = 'bank'`: a instalação tem uma política do banco só.

### risk_policy_version

Os parâmetros da política, um por coluna, para cada um ter tipo e validação próprios no schema.

| Coluna | Tipo | Restrição | Valor no modelo equilibrado |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `risk_policy_id` | INTEGER | FK `risk_policy` | |
| `version_number` | INTEGER | > 0. UNIQUE com `risk_policy_id`. Sai na API como `version` | 1 |
| `based_on_version_id` | INTEGER NULL | FK para a própria tabela. Nula só na versão 1 dos modelos | |
| `change_reason` | VARCHAR(255) | NOT NULL | "Modelo equilibrado" |
| `history_window_days` | INTEGER | > 0 | 90 |
| `source_baseline_reference_weight` | INTEGER | > 0. Peso k da mediana da população na base de comparação do pagador | 5 |
| `population_median_reference_weight` | INTEGER | > 0. Peso k do ticket médio de referência na mediana da população | 30 |
| `reference_average_ticket_individual_to_individual_cents` | BIGINT | > 0 | 26864 |
| `reference_average_ticket_individual_to_company_cents` | BIGINT | > 0 | 11242 |
| `reference_average_ticket_company_to_individual_cents` | BIGINT | > 0 | 54958 |
| `reference_average_ticket_company_to_company_cents` | BIGINT | > 0 | 540453 |
| `amount_rules_floor_cents` | BIGINT | >= 0 | 10000 |
| `new_account_age_days` | INTEGER | > 0 | 30 |
| `new_account_cap_individual_cents` | BIGINT | > 0 | 100000 |
| `new_account_cap_company_cents` | BIGINT | > 0 | 1000000 |
| `identity_family_cap` | INTEGER | > 0 | 50 |
| `velocity_family_cap` | INTEGER | > 0 | 40 |
| `amount_family_cap` | INTEGER | > 0 | 35 |
| `counterparty_family_cap` | INTEGER | > 0 | 70 |
| `counterparty_relationship_cap` | INTEGER | > 0 e <= `counterparty_family_cap` | 30 |
| `behavior_score_cap` | INTEGER | > 0 | 65 |
| `two_factor_score_threshold` | INTEGER | > 0 | 40 |
| `rejection_score_threshold` | INTEGER | > `two_factor_score_threshold` | 70 |
| `two_factor_validity_minutes` | INTEGER | > 0 | 10 |
| `destination_risk_alert_threshold` | INTEGER | > 0. Risco do recebedor a partir do qual sai o alerta | 30 |
| `short_term_window_minutes` | INTEGER | > 0 | 1440 |
| `requested_by` | VARCHAR(100) NULL | Quem pediu a edição no banco | |
| `risk_acknowledged` | BOOLEAN | DEFAULT false. Verdadeiro só com `requested_by` preenchido | false |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |

### risk_policy_rule_setting

Ajuste de cada regra editável em cada versão. Toda versão tem a lista completa (uma linha por regra que não é regulatória), então uma versão se lê sozinha, sem seguir a cadeia de versões anteriores.

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | SERIAL | PK |
| `risk_policy_version_id` | INTEGER | FK `risk_policy_version` |
| `rule_id` | INTEGER | FK `rule`. UNIQUE com a versão |
| `enabled` | BOOLEAN | NOT NULL |
| `points` | INTEGER NULL | Entre -100 e 100. Preenchida nas regras de pontuação e nos redutores |
| `threshold` | NUMERIC(12,2) NULL | > 0. Preenchida quando a regra tem `threshold_unit` |
| `company_threshold` | NUMERIC(12,2) NULL | > 0. Limite próprio quando o recebedor é PJ. Preenchida só nas regras que tratam PJ à parte |
| `window_minutes` | INTEGER NULL | > 0. Preenchida quando a regra tem `uses_window_minutes` |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

As regras regulatórias não têm linha aqui: os valores delas são de norma e ficam em constantes no código.

### risk_policy_guardrail

Faixa de segurança, semeada pela QI e fora do alcance do banco. Diz, para cada parâmetro e ajuste de regra, em que direção ele afrouxa a política e até onde o banco pode ir.

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | SERIAL | PK |
| `policy_parameter_name` | VARCHAR(80) NULL | UNIQUE. Preenchida se e somente se `rule_id` é nula |
| `rule_id` | INTEGER NULL | FK `rule`. UNIQUE com `rule_setting_field` |
| `rule_setting_field` | VARCHAR(20) NULL | CHECK em `points`, `threshold`, `company_threshold`, `window_minutes`. Preenchida se e somente se `rule_id` está |
| `loosening_direction` | VARCHAR(10) | CHECK em `higher`, `lower`: o lado que deixa passar mais Pix |
| `loosest_accepted_value` | NUMERIC(14,2) NULL | Além deste valor, a edição é recusada. Nula quando quem decide são os casos-âncora |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

Como a edição é julgada, sempre contra a política de referência (`balanced`, versão 1):
1. Desligar uma regra eliminatória é recusado (422 QIT001018). Desligar uma regra de pontuação é afrouxar; desligar um redutor é ficar mais rígido.
2. Valor além do `loosest_accepted_value` é recusado (422 QIT001018). Os limites cobrem o que muda se uma regra dispara: piso, multiplicadores, contagens, idades de conta, tetos de conta nova e os três limiares de decisão.
3. Pontos, tetos e limiares são julgados pelos casos-âncora: perfis de fraude conhecidos recalculados com a política proposta. Se algum deixa de chegar à decisão mínima, a edição é recusada (422 QIT001019).
4. Qualquer valor mais frouxo que a referência, dentro dos limites, exige `risk_acknowledged` e `requested_by` (422 QIT001020 sem eles). Ficar mais rígido nunca exige.

| Caso-âncora | Regras | Mínimo |
|---|---|---|
| Invasão de conta com valor alto | IP, local e canal nunca vistos (com 20 Pix de histórico), valor muito fora do padrão, destino novo acima do teto | `rejected` |
| Laranja marcado pela base | destino novo acima do teto, fan-in, várias contas, reprovado para outros, aparelho cadastrado | `two_factor_required` com alerta |
| Falsa central | valor muito fora do padrão, destino novo acima do teto, aparelho cadastrado | `two_factor_required` com alerta |

As janelas das regras, os pesos de credibilidade, a validade do 2FA e os tickets de referência ficam sem faixa nesta versão.

### pix_analysis

Tudo que chegou e a decisão do motor.

| Grupo | Coluna | Tipo | Restrição |
|---|---|---|---|
| Identidade | `id` | BIGSERIAL | PK, nunca sai da API |
| | `analysis_key` | UUID | UNIQUE. É o `key` da resposta |
| | `pix_id` | VARCHAR(64) | UNIQUE |
| | `payload_hash` | CHAR(64) | SHA-256 do JSON canônico (chaves em ordem), com documentos só com dígitos e letras, `channel` em minúsculas e `amount` inteiro. As datas entram como vieram |
| Valor e tempo | `amount_cents` | BIGINT | > 0 |
| | `transaction_date` | TIMESTAMPTZ | NOT NULL |
| | `transaction_utc_offset_minutes` | SMALLINT | Entre -720 e 840. O TIMESTAMPTZ guarda em UTC e perde o fuso; esta coluna preserva o horário local |
| Origem | `source_document_number` | VARCHAR(14) | 11 dígitos ou 14 caracteres alfanuméricos maiúsculos |
| | `source_person_type` | VARCHAR(10) | `individual` ou `company`, coerente com o tamanho do documento |
| | `source_branch` | VARCHAR(10) | |
| | `source_account_number` | VARCHAR(20) | |
| | `source_account_opening_date` | TIMESTAMPTZ | |
| Destino | `destination_participant_ispb` | CHAR(8) | `destination_account.participant`. Só dígitos (ISPB) |
| | `destination_branch` | VARCHAR(10) | |
| | `destination_account_number` | VARCHAR(20) | |
| | `destination_account_opening_date` | TIMESTAMPTZ | |
| | `destination_document_number` | VARCHAR(14) | Mesma regra do documento de origem |
| | `destination_person_type` | VARCHAR(10) | Mesma regra |
| Dispositivo | `source_device_id` | VARCHAR(100) | `source.device_id` do pedido |
| | `source_channel` | VARCHAR(30) | `source.channel`. Minúsculas, letras, dígitos e `_` |
| | `source_ip` | INET | `source.ip`. Valida IPv4 e IPv6 |
| | `source_latitude` | NUMERIC(8,6) NULL | `source.geolocation.latitude`. Entre -90 e 90 |
| | `source_longitude` | NUMERIC(9,6) NULL | `source.geolocation.longitude`. Entre -180 e 180. Nula junto com a latitude |
| Decisão | `decision_id` | INTEGER | FK `decision` |
| | `risk_score` | INTEGER NULL | >= 0. Nula quando uma regra eliminatória decidiu |
| | `destination_risk_score` | INTEGER NULL | >= 0. Risco do recebedor. Nula quando uma regra eliminatória decidiu |
| | `risk_policy_version_id` | INTEGER | FK `risk_policy_version`: a versão que decidiu |
| | `two_factor_expires_at` | TIMESTAMPTZ NULL | Preenchida só quando a decisão é 2FA. Congela a validade da versão que decidiu |
| Auditoria | `created_at` | TIMESTAMPTZ | DEFAULT now(). Nenhuma regra lê |

Índices: `(source_document_number, transaction_date)`, `(destination_document_number, transaction_date)`, `(source_device_id, transaction_date)` e `(source_person_type, destination_person_type, transaction_date)`.

### pix_analysis_rule_hit

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `pix_analysis_id` | BIGINT | FK `pix_analysis` |
| `rule_id` | INTEGER | FK `rule`. UNIQUE com a análise |
| `points` | INTEGER | NOT NULL. Negativo nos redutores, zero nas eliminatórias e regulatórias |
| `reason` | VARCHAR(255) | NOT NULL. Ex.: "conta de destino aberta há 3 dias" |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

### two_factor_confirmation

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `pix_analysis_id` | BIGINT | FK `pix_analysis`. UNIQUE: uma confirmação por análise |
| `result` | VARCHAR(10) | `confirmed` ou `denied` |
| `answered_at` | TIMESTAMPTZ | NOT NULL. Quando o pagador respondeu ao 2FA, confirmando ou recusando. Vem no corpo do pedido |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

A rota confere que a análise pediu 2FA e que `answered_at` fica entre `transaction_date` e `two_factor_expires_at`.

### registered_device

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `source_document_number` | VARCHAR(14) | UNIQUE com `device_id` |
| `device_id` | VARCHAR(100) | |
| `registration_origin` | VARCHAR(15) | `two_factor` ou `first_seen` |
| `registered_at` | TIMESTAMPTZ | `answered_at` do 2FA ou `transaction_date` do primeiro Pix aceito |
| `registration_pix_analysis_id` | BIGINT | FK `pix_analysis`: a análise que originou o cadastro |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

### source_nightly_limit

Limite noturno do pagador PF quando o banco cliente aprova um valor diferente do padrão de R$ 1.000. Sem linha, vale o padrão da norma.

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `source_document_number` | VARCHAR(14) | Só CPF |
| `nightly_limit_cents` | BIGINT | > 0 |
| `requested_at` | TIMESTAMPTZ | Quando o pagador pediu |
| `effective_at` | TIMESTAMPTZ | Aumento: pelo menos 24 h depois do pedido, como manda a norma. Redução: na hora do pedido |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

O limite que vale numa análise sai do pedido mais recente com `requested_at` até a data da transação: se ele já vale, é o valor dele; se é um aumento ainda pendente, vale o limite em vigor antes dele. Assim uma redução nunca é desfeita por um aumento pedido antes.

### accepted_pix (VIEW)

Análises com decisão `approved`, mais as com decisão `two_factor_required` e confirmação `confirmed`. Traz as colunas da análise e `acceptance_path` (`direct` ou `two_factor`). É de onde saem a mediana do pagador, a mediana da população, os destinos conhecidos, o teto habitual, a familiaridade de IP, local e canal e o volume mensal. Sem contador para atualizar e sempre reconstruível.

## Catálogo de regras e ajustes do modelo equilibrado

| Código | Tipo | Família | Pontos | Limite | Janela |
|---|---|---|---|---|---|
| `device_used_by_many_sources` | eliminatória (reprova) | | | 5 pagadores PF | 24 h |
| `impossible_travel_on_unregistered_device` | eliminatória (reprova) | | | 900 km/h | |
| `new_account_to_new_destination_far_above_cap` | eliminatória (reprova) | | | 5 × teto de conta nova | |
| `nightly_limit_exceeded` | regulatória (reprova) | | | Soma da noite PF para PF acima de R$ 1.000 ou do limite aprovado em `source_nightly_limit`, 20h às 6h | |
| `unregistered_device_limit_exceeded` | regulatória (2FA) | | | R$ 200 por Pix e R$ 1.000 por dia, fixo | |
| `impossible_travel` | pontuação | identidade | 40 | 900 km/h, a partir de 50 km | |
| `ip_unfamiliar` | pontuação | identidade | 10 (a definir) | k = 5 | |
| `location_unfamiliar` | pontuação | identidade | 10 (a definir) | k = 5 | |
| `channel_unfamiliar` | pontuação | identidade | 15 (a definir) | k = 5 | |
| `two_factor_denied_recently` | pontuação | identidade | 30 (a definir) | | 24 h |
| `new_account_above_cap` | pontuação | tempo | 40 | | |
| `burst_of_pix` | pontuação | tempo | 25 | 5 Pix; pagador PJ: 50 | 5 min |
| `amount_above_baseline` | pontuação | valor | 25 | 5 × base de comparação | |
| `amount_far_above_baseline` | pontuação | valor | 35 | 20 × base de comparação | |
| `monthly_volume_above_typical` | pontuação | valor | 20 | 3 × volume mensal típico | 30 dias |
| `destination_account_opened_very_recently` | pontuação | contraparte (relação) | 25 | 7 dias | |
| `destination_account_opened_recently` | pontuação | contraparte (relação) | 20 | 30 dias | |
| `new_destination_above_usual_ceiling` | pontuação | contraparte (relação) | 30 | 1 × teto habitual; recebedor PJ: 3 ×; a partir do piso das regras de valor | |
| `destination_receiving_from_many_sources` | pontuação | contraparte (base) | 30 | 5 pagadores com Pix a partir do piso das regras de valor, só recebedor PF | 1 h |
| `destination_rejected_for_other_sources` | pontuação | contraparte (base) | 20 | 2 outros pagadores com 2FA recusado ou reprovação com regra de contraparte | 7 dias |
| `destination_document_in_many_accounts` | pontuação | contraparte (base) | 30 | 3 contas de destino; recebedor PJ: 10 | 24 h |
| `same_owner` | redutor | | -30 | | |
| `known_destination` | redutor | | -20 | 3 Pix aceitos | |
| `long_registered_device` | redutor | | -10 | 30 dias | |

Regras de convivência:
- As duas regras de conta de destino recente são exclusivas: dispara só a mais grave.
- A mediana do pagador e a mediana da população são calculadas pelo par pagador → recebedor do Pix analisado. O início frio continua sendo do pagador inteiro; um par sem histórico só pesa mais o ticket médio de referência.
- Em início frio não pontuam: familiaridade de IP, local e canal, e a família valor (valor fora do padrão e volume mensal). O limite do dispositivo não cadastrado vale também no início frio: o primeiro Pix acima de R$ 200 pede 2FA, e o 2FA confirmado cadastra o aparelho.
- Familiaridade só pontua IP, local ou canal nunca vistos nos Pix aceitos do pagador, com peso que cresce com o histórico: `piso(pontos × N / (N + k))`, N = Pix aceitos do pagador. O que já foi usado não pontua, para o histórico só tirar fricção.
- Se o primeiro Pix aceito do pagador veio por 2FA confirmado, a origem do cadastro do dispositivo é `two_factor`.
- `destination_account_opened_very_recently` vale 25, abaixo do limiar de alerta: conta de destino nova sozinha não gera alerta, mas gera com qualquer outro sinal.
- `destination_rejected_for_other_sources` só soma risco e nunca reprova sozinha. Conta os 2FA recusados e os Pix reprovados em que disparou alguma regra de contraparte ou `new_account_to_new_destination_far_above_cap`. Reprovação por motivo só do pagador (limite noturno, dispositivo compartilhado, viagem impossível) não diz nada sobre o recebedor e fica de fora. Ignora as análises em que ela mesma disparou, para não se realimentar.
- `destination_receiving_from_many_sources` só conta pagadores cujo Pix atingiu `amount_rules_floor_cents`, para racha de conta e vaquinha de valor baixo não parecerem conta laranja.
- `amount_above_baseline` e `amount_far_above_baseline` são exclusivas: dispara só a mais grave. O multiplicador da segunda precisa ser maior que o da primeira.
- `new_destination_above_usual_ceiling` vale 30, acima do limiar de alerta: destino novo bem acima do teto habitual gera alerta sozinho, que é o que a vítima de falsa central precisa ver. Para recebedor PJ, o limite é 3 vezes o teto, para a primeira compra numa loja não gerar alerta à toa.
- Risco do recebedor: os redutores abatem só os sinais da relação (`counterparty_signal = 'relationship'`). Os sinais da base (`counterparty_signal = 'base'`) entram inteiros. `destination_risk_score = max(0, sinais da relação - mesma titularidade - destino conhecido) + sinais da base`.
- O limite de PJ fica em `company_threshold`: o recebedor PJ em `destination_document_in_many_accounts` e o pagador PJ em `burst_of_pix`, porque empresa paga em lote. O banco muda criando uma versão nova da política.
- `device_used_by_many_sources` conta só pagadores PF: empresas que pagam pelo mesmo computador, como um escritório de contabilidade, não são uma fazenda de aparelhos.
- A viagem impossível compara o Pix analisado com o último Pix aceito do pagador com geolocalização, e só a partir de 50 km. Uma tentativa reprovada de um invasor não contamina o próximo Pix do dono, e a imprecisão da localização por wi-fi ou antena não vira viagem.
- O teto habitual nunca fica abaixo da base de comparação e ignora os Pix para conta própria e os aceitos na janela de curto prazo.
- Valor acumulado de cada regra de valor (princípio 8):
  - total do pagador: `new_account_above_cap`, `nightly_limit_exceeded` (soma da noite) e `unregistered_device_limit_exceeded` (soma do dia no mesmo dispositivo);
  - para o mesmo recebedor: `amount_above_baseline`, `amount_far_above_baseline`, `new_destination_above_usual_ceiling` e `new_account_to_new_destination_far_above_cap`;
  - o piso das regras de valor também é comparado com o acumulado, para dez Pix de R$ 99 não escaparem dele, e vale também para `new_destination_above_usual_ceiling`.

## Como as regras viram decisão

1. Regras eliminatórias. Se alguma dispara, as que dispararam são gravadas, a decisão é `rejected` e a análise termina aqui. `risk_score` e `destination_risk_score` ficam nulos.
2. Regras de pontuação e redutores. Cada família é limitada ao seu teto e perde os redutores que a desmentem, sem ficar abaixo de zero: o aparelho cadastrado abate a identidade, o destino conhecido abate os sinais da relação, e a mesma titularidade abate os sinais da relação e o valor.
   - Comportamento = velocidade + valor + relação, limitado a `behavior_score_cap` (65). Os sinais da relação têm antes o próprio teto, `counterparty_relationship_cap` (30).
   - Evidência = identidade + a parte dos sinais da base na contraparte. A contraparte inteira (relação mais base) é limitada a `counterparty_family_cap` (70).
   - Pontuação de risco = identidade + comportamento + parte da base. A faixa sai dos limiares da versão vigente.
   - Consequência: no modelo equilibrado, comportamento atípico sozinho chega no máximo a 65 e pede 2FA. Reprovar exige evidência: dúvida de identidade, sinais da base sobre o recebedor, uma regra eliminatória ou o limite noturno.
3. Regras regulatórias. O limite noturno estourado reprova; o limite do dispositivo não cadastrado pede no mínimo 2FA. Vale a mais severa entre elas e a faixa da pontuação.
4. Risco do recebedor. Sinais da relação menos os redutores de mesma titularidade e destino conhecido, nunca abaixo de zero, mais os sinais da base. Se atinge `destination_risk_alert_threshold`, sai um alerta em `metadata.alerts`. Não muda a decisão.

## Modelos de política (carga inicial)

- `conservative`, `balanced` e `permissive`, versão 1, `kind = 'template'`. Diferem no apetite de risco:

| Parâmetro ou ajuste | conservative | balanced | permissive |
|---|---|---|---|
| `two_factor_score_threshold` | 35 | 40 | 45 |
| `rejection_score_threshold` | 60 | 70 | 80 |
| `destination_risk_alert_threshold` | 25 | 30 | 30 |
| `behavior_score_cap` | 105 (sem limite na prática) | 65 | 75 |
| `amount_above_baseline` | 3 × | 5 × | 10 × |
| `amount_far_above_baseline` | 10 × | 20 × | 40 × |

  No conservador, comportamento atípico pode reprovar sozinho: ele reprova a falsa central sem evidência da base, e também o aluguel pago a um locador novo. No equilibrado e no permissivo, o teto do comportamento fica abaixo do limiar de reprovação.
- `bank`, versão 1, `kind = 'bank'`, copiada do `balanced` (`based_on_version_id` aponta para ele).

## O que cada regra lê

| Conta | Regras | Análises que entram |
|---|---|---|
| Histórico do pagador | Mediana, teto habitual, destino conhecido, familiaridade, volume mensal | `accepted_pix` |
| Consumo de limite | Limite noturno, limite do dispositivo não cadastrado | `accepted_pix` mais 2FA pendentes |
| Valor acumulado de curto prazo | Todas as regras de valor (princípio 8) | `accepted_pix` mais 2FA pendentes do pagador na janela de curto prazo |
| Limite noturno aprovado | `nightly_limit_exceeded` | `source_nightly_limit` |
| Tentativas | Rajada, dispositivo compartilhado, fan-in, recebedor em várias contas | Todas as análises |
| Reprovações do recebedor | `destination_rejected_for_other_sources` | 2FA recusados e análises reprovadas com regra de contraparte disparada, de outros pagadores para o mesmo documento de recebedor |
| 2FA recusado | `two_factor_denied_recently` | `two_factor_confirmation` com `denied` |
| Cadastro | Limite do dispositivo, viagem impossível em dispositivo não cadastrado, dispositivo cadastrado há muito tempo | `registered_device` |

## Rotas que dependem deste modelo

| Rota | Respostas |
|---|---|
| `POST /pix/transaction` | 201 análise nova; 200 mesmo id e mesmo conteúdo; 409 mesmo id com outro conteúdo |
| `GET /pix/transaction/{id}` | 200 com `status` = decisão, `metadata.two_factor` e `metadata.alerts`; 404 |
| `POST /pix/transaction/{id}/two-factor` | 201; 200 mesmo resultado repetido; 409 já confirmado com outro resultado ou análise sem 2FA; 422 fora da validade; 404 |
| `POST /sources/{document}/nightly-limit` | 201. Corpo: `nightly_limit_cents` e `requested_at`. O banco chama depois de aprovar; o motor calcula `effective_at` |
| `GET /risk-policy` | Versão vigente: parâmetros e ajustes de regra |
| `GET /risk-policy/versions/{version}` | Uma versão antiga, para auditoria |
| `POST /risk-policy/versions` | 201 versão nova. Corpo: `change_reason`, `based_on_template` opcional, `requested_by` e `risk_acknowledged` opcionais, parâmetros e ajustes que mudam. O resto é herdado. Edição simultânea cai no UNIQUE da versão: 409. Faixas de segurança e casos-âncora: 422 |
| `GET /risk-policy/guardrails` | A política de referência, as faixas de segurança com o valor recomendado e o limite de cada uma, e os casos-âncora |

## Garantido pelo código, não pelo banco

As regras abaixo valem para os dados gravados, mas não são CHECK no banco: quem garante é o schema JSON (antes de qualquer consulta, 400) ou o controller (422), e cada uma tem teste por HTTP.

| Regra | Onde é garantida |
|---|---|
| Valor do Pix e limite noturno maiores que zero | Schema (`amount_cents`, mínimo 1) |
| Fuso entre -12:00 e +14:00 e ano entre 1900 e 2999 | `parsed_datetime_with_offset` (422 QIT001004) |
| Documento é CPF ou CNPJ válido, guardado sem pontuação e em maiúsculas | Schema e `required_document` (422 QIT001003) |
| Tipo de pessoa coerente com o documento | `person_type_of`, que deriva um do outro |
| ISPB com 8 dígitos, agência e conta só com dígitos | Schema |
| Conta aberta até a data da transação | `pix_under_analysis_from` (422 QIT001006) |
| Canal em minúsculas, letras, dígitos e `_` | Schema e normalização para minúsculas |
| Latitude e longitude no intervalo, finitas e sempre juntas | Schema e `finite_coordinate` |
| `risk_score` e `destination_risk_score` nunca negativos e sempre juntos | `AnalysisDecision`: cada parte é limitada a zero, e só a regra eliminatória deixa as duas nulas |
| `two_factor_expires_at` preenchido se e somente se a decisão é `two_factor_required`, e depois da data da transação | `AnalysisDecision`, com `two_factor_validity_minutes` de no mínimo 1 no schema |
| Motivo de regra disparada nunca em branco | Cada regra do catálogo monta o seu motivo |
| Resultado do 2FA é `confirmed` ou `denied` | Schema |
| Origem do cadastro do aparelho é `two_factor` ou `first_seen` | `PixAnalysisController`, que só grava esses dois |
| Limite noturno só para CPF, e passa a valer no pedido ou depois | `SourceController` (422 QIT001010) e `nightly_limit_effective_at` |
| Parâmetros da política positivos, piso maior ou igual a zero, motivo da mudança não vazio | Schema |
| Limiar de reprovação acima do de 2FA; teto da relação até o teto da contraparte | `ensure_consistent_policy` (422 QIT001016) |
| Aceite do risco só com quem pediu | Schema (`dependencies`) |
| Número da versão sequencial a partir de 1 | `create_bank_policy_version`, com o UNIQUE da versão segurando edições simultâneas (409) |
| Pontos de -100 a 100; limites e janelas maiores que zero | Schema; sinal dos pontos por tipo de regra em `ensure_consistent_policy` |
| `risk_policy_version_id` da análise aponta para uma versão da política `bank` | `PixAnalysisController`, que só busca a versão vigente do banco |
| `registered_device.source_document_number` é o mesmo da análise de origem | `PixAnalysisController` |
| O ajuste de cada regra segue o catálogo: limite nulo quando `threshold_unit` é nulo, janela nula quando `uses_window_minutes` é falso, e toda versão tem as 22 linhas | `RiskPolicyController` |

`GET /risk-policy/templates` entra na entrega: os testes exigem.

## Em aberto

- Pontos das regras marcadas "a definir".
- Para o README: premissa de confiança nas datas (quem chama é o backend do banco), meta de latência e o que fazer se o motor não responder.
