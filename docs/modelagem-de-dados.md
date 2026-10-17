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
4. **Trava por pagador.** A análise e a confirmação de 2FA começam com `pg_advisory_xact_lock` no documento do pagador. Pix simultâneos do mesmo pagador enxergam uns aos outros.
5. **Um COMMIT por fato.** Análise, regras disparadas e cadastro `first_seen` entram juntos. Confirmação de 2FA e cadastro `two_factor` entram juntos. Versão da política e todos os seus ajustes de regra entram juntos.
6. **Nenhum id do banco sai da API.** Para fora vão `analysis_key` (UUID), `pix_id`, nome da política e número da versão.
7. **Dinheiro em centavos** (BIGINT).
8. **Nada se burla fracionando.** Toda regra que compara um valor com um limite compara o maior entre o Pix analisado e o valor acumulado de curto prazo: o Pix analisado mais os Pix aceitos e 2FA pendentes do mesmo pagador dentro de `short_term_window_minutes`. Cada regra diz qual acumulado usa: o total do pagador ou só o que foi para o mesmo recebedor. Dois Pix de R$ 1.000 contam como R$ 2.000.

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
| `code` | VARCHAR(80) | UNIQUE |
| `kind` | VARCHAR(20) | CHECK em `scoring`, `reducer`, `eliminatory`, `regulatory` |
| `family` | VARCHAR(20) NULL | CHECK em `identity`, `velocity`, `amount`, `counterparty`. Preenchida se e somente se `kind = 'scoring'` |
| `forced_decision_id` | INTEGER NULL | FK `decision`. Preenchida se e somente se `kind` for `eliminatory` ou `regulatory` |
| `threshold_unit` | VARCHAR(30) NULL | CHECK em `count`, `days`, `km_per_hour`, `multiplier`, `credibility_weight`. Nula quando a regra não tem limite |
| `uses_window` | BOOLEAN | A regra tem janela própria em minutos |
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

Os parâmetros da política, um por coluna, para cada um ter tipo e CHECK próprios.

| Coluna | Tipo | Restrição | Valor no modelo equilibrado |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `risk_policy_id` | INTEGER | FK `risk_policy` | |
| `version` | INTEGER | > 0. UNIQUE com `risk_policy_id` | 1 |
| `based_on_version_id` | INTEGER NULL | FK para a própria tabela. Nula só na versão 1 dos modelos | |
| `change_reason` | VARCHAR(255) | NOT NULL | "Modelo equilibrado" |
| `history_window_days` | INTEGER | > 0 | 90 |
| `source_history_weight` | INTEGER | > 0 | 5 |
| `population_median_weight` | INTEGER | > 0 | 30 |
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
| `counterparty_family_cap` | INTEGER | > 0 | 40 |
| `two_factor_score_threshold` | INTEGER | > 0 | 40 |
| `rejection_score_threshold` | INTEGER | > `two_factor_score_threshold` | 70 |
| `two_factor_validity_minutes` | INTEGER | > 0 | 10 |
| `destination_alert_threshold` | INTEGER | > 0 | 30 |
| `short_term_window_minutes` | INTEGER | > 0 | 1440 |
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
| `window_minutes` | INTEGER NULL | > 0. Preenchida quando a regra tem `uses_window` |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

As regras regulatórias não têm linha aqui: os valores delas são de norma e ficam em constantes no código.

### pix_analysis

Tudo que chegou e a decisão do motor.

| Grupo | Coluna | Tipo | Restrição |
|---|---|---|---|
| Identidade | `id` | BIGSERIAL | PK, nunca sai da API |
| | `analysis_key` | UUID | UNIQUE. É o `key` da resposta |
| | `pix_id` | VARCHAR(64) | UNIQUE |
| | `payload_hash` | CHAR(64) | SHA-256 do corpo normalizado |
| Valor e tempo | `amount_cents` | BIGINT | > 0 |
| | `transaction_date` | TIMESTAMPTZ | NOT NULL |
| | `transaction_utc_offset_minutes` | SMALLINT | Entre -720 e 840. O TIMESTAMPTZ guarda em UTC e perde o fuso; esta coluna preserva o horário local |
| Origem | `source_document` | VARCHAR(14) | 11 dígitos ou 14 caracteres alfanuméricos maiúsculos |
| | `source_person_type` | VARCHAR(10) | CHECK em `individual`, `company`, coerente com o tamanho do documento |
| | `source_branch` | VARCHAR(10) | |
| | `source_account_number` | VARCHAR(20) | |
| | `source_account_opening_date` | TIMESTAMPTZ | |
| Destino | `destination_participant` | CHAR(8) | Só dígitos (ISPB) |
| | `destination_branch` | VARCHAR(10) | |
| | `destination_account_number` | VARCHAR(20) | |
| | `destination_account_opening_date` | TIMESTAMPTZ | |
| | `destination_document` | VARCHAR(14) | Mesma regra do documento de origem |
| | `destination_person_type` | VARCHAR(10) | Mesma regra |
| Dispositivo | `device_id` | VARCHAR(100) | |
| | `channel` | VARCHAR(30) | Minúsculas, letras, dígitos e `_` |
| | `ip` | INET | Valida IPv4 e IPv6 |
| | `latitude` | NUMERIC(8,6) NULL | Entre -90 e 90 |
| | `longitude` | NUMERIC(9,6) NULL | Entre -180 e 180. Nula junto com a latitude |
| Decisão | `decision_id` | INTEGER | FK `decision` |
| | `risk_score` | INTEGER NULL | >= 0. Nula quando uma regra eliminatória decidiu |
| | `destination_risk` | INTEGER NULL | >= 0. Risco do recebedor. Nula quando uma regra eliminatória decidiu |
| | `risk_policy_version_id` | INTEGER | FK `risk_policy_version`: a versão que decidiu |
| | `two_factor_expires_at` | TIMESTAMPTZ NULL | Preenchida só quando a decisão é 2FA. Congela a validade da versão que decidiu |
| Auditoria | `created_at` | TIMESTAMPTZ | DEFAULT now(). Nenhuma regra lê |

Índices: `(source_document, transaction_date)`, `(destination_document, transaction_date)`, `(device_id, transaction_date)` e `(source_person_type, destination_person_type, transaction_date)`.

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
| `result` | VARCHAR(10) | CHECK em `confirmed`, `denied` |
| `confirmed_at` | TIMESTAMPTZ | NOT NULL. Vem no corpo do pedido |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

A rota confere que a análise pediu 2FA e que `confirmed_at` fica entre `transaction_date` e `two_factor_expires_at`.

### registered_device

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `source_document` | VARCHAR(14) | UNIQUE com `device_id` |
| `device_id` | VARCHAR(100) | |
| `registration_origin` | VARCHAR(15) | CHECK em `two_factor`, `first_seen` |
| `registered_at` | TIMESTAMPTZ | `confirmed_at` do 2FA ou `transaction_date` do primeiro Pix aceito |
| `pix_analysis_id` | BIGINT | FK `pix_analysis`: a análise que originou o cadastro |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

### source_nightly_limit

Limite noturno do pagador PF quando o banco cliente aprova um valor diferente do padrão de R$ 1.000. Sem linha, vale o padrão da norma.

| Coluna | Tipo | Restrição |
|---|---|---|
| `id` | BIGSERIAL | PK |
| `source_document` | VARCHAR(14) | Só CPF |
| `nightly_limit_cents` | BIGINT | > 0 |
| `requested_at` | TIMESTAMPTZ | Quando o pagador pediu |
| `effective_at` | TIMESTAMPTZ | Aumento: pelo menos 24 h depois do pedido, como manda a norma. Redução: na hora do pedido |
| `created_at` | TIMESTAMPTZ | DEFAULT now() |

O limite que vale numa análise é a linha com o maior `effective_at` até a data da transação.

### accepted_pix (VIEW)

Análises com decisão `approved`, mais as com decisão `two_factor_required` e confirmação `confirmed`. Traz as colunas da análise e `acceptance` (`direct` ou `two_factor`). É de onde saem a mediana do pagador, a mediana da população, os destinos conhecidos, o teto habitual, a familiaridade de IP, local e canal e o volume mensal. Sem contador para atualizar e sempre reconstruível.

## Catálogo de regras e ajustes do modelo equilibrado

| Código | Tipo | Família | Pontos | Limite | Janela |
|---|---|---|---|---|---|
| `device_used_by_many_sources` | eliminatória (reprova) | | | 5 pagadores | 24 h |
| `impossible_travel_on_unregistered_device` | eliminatória (reprova) | | | 900 km/h | |
| `new_account_to_new_destination_far_above_cap` | eliminatória (reprova) | | | 5 × teto de conta nova | |
| `nightly_limit_exceeded` | regulatória (reprova) | | | Soma da noite PF para PF acima de R$ 1.000 ou do limite aprovado em `source_nightly_limit`, 20h às 6h | |
| `unregistered_device_limit_exceeded` | regulatória (2FA) | | | R$ 200 por Pix e R$ 1.000 por dia, fixo | |
| `impossible_travel` | pontuação | identidade | 40 | 900 km/h | |
| `ip_unfamiliar` | pontuação | identidade | 10 (a definir) | k = 5 | |
| `location_unfamiliar` | pontuação | identidade | 10 (a definir) | k = 5 | |
| `channel_unfamiliar` | pontuação | identidade | 15 (a definir) | k = 5 | |
| `two_factor_denied_recently` | pontuação | identidade | 30 (a definir) | | 24 h |
| `new_account_above_cap` | pontuação | tempo | 40 | | |
| `burst_of_pix` | pontuação | tempo | 25 | 5 Pix | 5 min |
| `amount_above_baseline` | pontuação | valor | 25 | 5 × base de comparação | |
| `monthly_volume_above_typical` | pontuação | valor | 20 | 3 × volume mensal típico | 30 dias |
| `destination_account_opened_very_recently` | pontuação | contraparte | 30 | 7 dias | |
| `destination_account_opened_recently` | pontuação | contraparte | 20 | 30 dias | |
| `new_destination_above_usual_ceiling` | pontuação | contraparte | 25 | | |
| `destination_receiving_from_many_sources` | pontuação | contraparte | 30 | 5 pagadores, só recebedor PF | 1 h |
| `destination_rejected_for_other_sources` | pontuação | contraparte | 20 | 2 outros pagadores | 7 dias |
| `destination_document_in_many_accounts` | pontuação | contraparte | 30 | 3 contas de destino; recebedor PJ: 10 | 24 h |
| `same_owner` | redutor | | -30 | | |
| `known_destination` | redutor | | -20 | 3 Pix aceitos | |
| `long_registered_device` | redutor | | -10 | 30 dias | |

Regras de convivência:
- As duas regras de conta de destino recente são exclusivas: dispara só a mais grave.
- A mediana do pagador e a mediana da população são calculadas pelo par pagador → recebedor do Pix analisado. O início frio continua sendo do pagador inteiro; um par sem histórico só pesa mais o ticket médio de referência.
- Em início frio não pontuam: familiaridade de IP, local e canal, e a família valor (valor fora do padrão e volume mensal). O limite do dispositivo não cadastrado também não dispara.
- Se o primeiro Pix aceito do pagador veio por 2FA confirmado, a origem do cadastro do dispositivo é `two_factor`.
- `destination_rejected_for_other_sources` só soma risco, nunca reprova sozinha, e não conta as análises em que ela mesma disparou, para não se realimentar.
- O limite de PJ em `destination_document_in_many_accounts` fica em `company_threshold` e o banco aumenta criando uma versão nova da política.
- Valor acumulado de cada regra de valor (princípio 8):
  - total do pagador: `new_account_above_cap`, `nightly_limit_exceeded` (soma da noite) e `unregistered_device_limit_exceeded` (soma do dia no mesmo dispositivo);
  - para o mesmo recebedor: `amount_above_baseline`, `new_destination_above_usual_ceiling` e `new_account_to_new_destination_far_above_cap`;
  - o piso das regras de valor também é comparado com o acumulado, para dez Pix de R$ 99 não escaparem dele.

## Como as regras viram decisão

1. Regras eliminatórias. Se alguma dispara, as que dispararam são gravadas, a decisão é `rejected` e a análise termina aqui. `risk_score` e `destination_risk` ficam nulos.
2. Regras de pontuação e redutores. Pontuação de risco = soma de cada família limitada ao seu teto, menos os redutores, nunca abaixo de zero. A faixa sai dos limiares da versão vigente.
3. Regras regulatórias. O limite noturno estourado reprova; o limite do dispositivo não cadastrado pede no mínimo 2FA. Vale a mais severa entre elas e a faixa da pontuação.
4. Risco do recebedor. Se atinge `destination_alert_threshold`, sai um alerta em `metadata.alerts`. Não muda a decisão.

## Modelos de política (carga inicial)

- `conservative`, `balanced` e `permissive`, versão 1, `kind = 'template'`. Diferem só no limite de `amount_above_baseline`: 3, 5 e 10.
- `bank`, versão 1, `kind = 'bank'`, copiada do `balanced` (`based_on_version_id` aponta para ele).

## O que cada regra lê

| Conta | Regras | Análises que entram |
|---|---|---|
| Histórico do pagador | Mediana, teto habitual, destino conhecido, familiaridade, volume mensal | `accepted_pix` |
| Consumo de limite | Limite noturno, limite do dispositivo não cadastrado | `accepted_pix` mais 2FA pendentes |
| Valor acumulado de curto prazo | Todas as regras de valor (princípio 8) | `accepted_pix` mais 2FA pendentes do pagador na janela de curto prazo |
| Limite noturno aprovado | `nightly_limit_exceeded` | `source_nightly_limit` |
| Tentativas | Rajada, dispositivo compartilhado, fan-in, recebedor em várias contas | Todas as análises |
| Reprovações do recebedor | `destination_rejected_for_other_sources` | Análises reprovadas e 2FA recusados de outros pagadores para o mesmo documento de recebedor |
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
| `POST /risk-policy/versions` | 201 versão nova. Corpo: `change_reason`, `based_on_template` opcional, parâmetros e ajustes que mudam. O resto é herdado. Edição simultânea cai no UNIQUE da versão: 409 |

## Em aberto

- Pontos das regras marcadas "a definir".
- Se `GET /risk-policy/templates` entra, para o banco ver os modelos antes de escolher.
