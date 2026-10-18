CREATE TABLE decision(
    id                              SERIAL PRIMARY KEY,
    enumerator                      VARCHAR(30) NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(enumerator)
);

CREATE TABLE rule(
    id                              SERIAL PRIMARY KEY,
    code                            VARCHAR(80) NOT NULL,
    kind                            VARCHAR(20) NOT NULL,
    family                          VARCHAR(20),
    counterparty_signal             VARCHAR(15),
    forced_decision_id              INTEGER REFERENCES decision(id),
    threshold_unit                  VARCHAR(30),
    uses_window_minutes             BOOLEAN NOT NULL,
    uses_company_threshold          BOOLEAN NOT NULL DEFAULT false,
    description                     VARCHAR(255) NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(code),
    CONSTRAINT ck_rule_kind CHECK (kind IN ('scoring', 'reducer', 'eliminatory', 'regulatory')),
    CONSTRAINT ck_rule_family CHECK (family IN ('identity', 'velocity', 'amount', 'counterparty')),
    CONSTRAINT ck_rule_threshold_unit CHECK (threshold_unit IN ('count', 'days', 'km_per_hour', 'multiplier', 'credibility_weight')),
    CONSTRAINT ck_rule_counterparty_signal CHECK (counterparty_signal IN ('relationship', 'base')),
    CONSTRAINT ck_rule_family_only_for_scoring CHECK ((kind = 'scoring') = (family IS NOT NULL)),
    CONSTRAINT ck_rule_counterparty_signal_only_for_counterparty CHECK ((family IS NOT DISTINCT FROM 'counterparty') = (counterparty_signal IS NOT NULL)),
    CONSTRAINT ck_rule_forced_decision_only_for_eliminatory_and_regulatory CHECK ((kind IN ('eliminatory', 'regulatory')) = (forced_decision_id IS NOT NULL)),
    CONSTRAINT ck_rule_regulatory_without_settings CHECK (kind <> 'regulatory' OR (threshold_unit IS NULL AND NOT uses_window_minutes AND NOT uses_company_threshold))
);

CREATE TABLE risk_policy(
    id                              SERIAL PRIMARY KEY,
    name                            VARCHAR(50) NOT NULL,
    kind                            VARCHAR(10) NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name),
    CONSTRAINT ck_risk_policy_kind CHECK (kind IN ('template', 'bank'))
);

CREATE UNIQUE INDEX uq_risk_policy_single_bank ON risk_policy(kind) WHERE kind = 'bank';

CREATE TABLE risk_policy_version(
    id                                                          SERIAL PRIMARY KEY,
    risk_policy_id                                              INTEGER NOT NULL REFERENCES risk_policy(id),
    version_number                                              INTEGER NOT NULL,
    based_on_version_id                                         INTEGER REFERENCES risk_policy_version(id),
    change_reason                                               VARCHAR(255) NOT NULL,
    history_window_days                                         INTEGER NOT NULL,
    source_baseline_reference_weight                            INTEGER NOT NULL,
    population_median_reference_weight                          INTEGER NOT NULL,
    reference_average_ticket_individual_to_individual_cents     BIGINT NOT NULL,
    reference_average_ticket_individual_to_company_cents        BIGINT NOT NULL,
    reference_average_ticket_company_to_individual_cents        BIGINT NOT NULL,
    reference_average_ticket_company_to_company_cents           BIGINT NOT NULL,
    amount_rules_floor_cents                                    BIGINT NOT NULL,
    new_account_age_days                                        INTEGER NOT NULL,
    new_account_cap_individual_cents                            BIGINT NOT NULL,
    new_account_cap_company_cents                               BIGINT NOT NULL,
    identity_family_cap                                         INTEGER NOT NULL,
    velocity_family_cap                                         INTEGER NOT NULL,
    amount_family_cap                                           INTEGER NOT NULL,
    counterparty_family_cap                                     INTEGER NOT NULL,
    counterparty_relationship_cap                               INTEGER NOT NULL,
    behavior_score_cap                                          INTEGER NOT NULL,
    two_factor_score_threshold                                  INTEGER NOT NULL,
    rejection_score_threshold                                   INTEGER NOT NULL,
    two_factor_validity_minutes                                 INTEGER NOT NULL,
    destination_risk_alert_threshold                            INTEGER NOT NULL,
    short_term_window_minutes                                   INTEGER NOT NULL,
    requested_by                                                VARCHAR(100),
    risk_acknowledged                                           BOOLEAN NOT NULL DEFAULT false,
    created_at                                                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(risk_policy_id, version_number),
    CONSTRAINT ck_risk_policy_version_positive_version_number CHECK (version_number > 0),
    CONSTRAINT ck_risk_policy_version_change_reason CHECK (char_length(btrim(change_reason)) > 0),
    CONSTRAINT ck_risk_policy_version_positive_windows CHECK (history_window_days > 0 AND short_term_window_minutes > 0 AND two_factor_validity_minutes > 0),
    CONSTRAINT ck_risk_policy_version_positive_weights CHECK (source_baseline_reference_weight > 0 AND population_median_reference_weight > 0),
    CONSTRAINT ck_risk_policy_version_positive_reference_tickets CHECK (
        reference_average_ticket_individual_to_individual_cents > 0
        AND reference_average_ticket_individual_to_company_cents > 0
        AND reference_average_ticket_company_to_individual_cents > 0
        AND reference_average_ticket_company_to_company_cents > 0
    ),
    CONSTRAINT ck_risk_policy_version_amount_rules_floor CHECK (amount_rules_floor_cents >= 0),
    CONSTRAINT ck_risk_policy_version_new_account CHECK (new_account_age_days > 0 AND new_account_cap_individual_cents > 0 AND new_account_cap_company_cents > 0),
    CONSTRAINT ck_risk_policy_version_positive_family_caps CHECK (identity_family_cap > 0 AND velocity_family_cap > 0 AND amount_family_cap > 0 AND counterparty_family_cap > 0),
    CONSTRAINT ck_risk_policy_version_relationship_cap CHECK (counterparty_relationship_cap > 0 AND counterparty_relationship_cap <= counterparty_family_cap),
    CONSTRAINT ck_risk_policy_version_behavior_score_cap CHECK (behavior_score_cap > 0),
    CONSTRAINT ck_risk_policy_version_score_thresholds CHECK (two_factor_score_threshold > 0 AND rejection_score_threshold > two_factor_score_threshold),
    CONSTRAINT ck_risk_policy_version_destination_risk_alert_threshold CHECK (destination_risk_alert_threshold > 0),
    CONSTRAINT ck_risk_policy_version_acknowledged_by_someone CHECK (NOT risk_acknowledged OR requested_by IS NOT NULL)
);

CREATE TABLE risk_policy_guardrail(
    id                              SERIAL PRIMARY KEY,
    policy_parameter_name           VARCHAR(80),
    rule_id                         INTEGER REFERENCES rule(id),
    rule_setting_field              VARCHAR(20),
    loosening_direction             VARCHAR(10) NOT NULL,
    loosest_accepted_value          NUMERIC(14,2),
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(policy_parameter_name),
    UNIQUE(rule_id, rule_setting_field),
    CONSTRAINT ck_risk_policy_guardrail_target CHECK ((policy_parameter_name IS NULL) <> (rule_id IS NULL)),
    CONSTRAINT ck_risk_policy_guardrail_rule_setting_field_with_rule CHECK ((rule_id IS NULL) = (rule_setting_field IS NULL)),
    CONSTRAINT ck_risk_policy_guardrail_rule_setting_field CHECK (rule_setting_field IN ('points', 'threshold', 'company_threshold', 'window_minutes')),
    CONSTRAINT ck_risk_policy_guardrail_loosening_direction CHECK (loosening_direction IN ('higher', 'lower'))
);

CREATE TABLE risk_policy_rule_setting(
    id                              SERIAL PRIMARY KEY,
    risk_policy_version_id          INTEGER NOT NULL REFERENCES risk_policy_version(id),
    rule_id                         INTEGER NOT NULL REFERENCES rule(id),
    enabled                         BOOLEAN NOT NULL,
    points                          INTEGER,
    threshold                       NUMERIC(12,2),
    window_minutes                  INTEGER,
    company_threshold               NUMERIC(12,2),
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(risk_policy_version_id, rule_id),
    CONSTRAINT ck_risk_policy_rule_setting_points CHECK (points BETWEEN -100 AND 100),
    CONSTRAINT ck_risk_policy_rule_setting_threshold CHECK (threshold > 0),
    CONSTRAINT ck_risk_policy_rule_setting_window_minutes CHECK (window_minutes > 0),
    CONSTRAINT ck_risk_policy_rule_setting_company_threshold CHECK (company_threshold > 0)
);

CREATE TABLE pix_analysis(
    id                                  BIGSERIAL PRIMARY KEY,
    analysis_key                        UUID NOT NULL,
    pix_id                              VARCHAR(64) NOT NULL,
    payload_hash                        CHAR(64) NOT NULL,
    amount_cents                        BIGINT NOT NULL,
    transaction_date                    TIMESTAMPTZ NOT NULL,
    transaction_utc_offset_minutes      SMALLINT NOT NULL,
    source_document_number              VARCHAR(14) NOT NULL,
    source_person_type                  VARCHAR(10) NOT NULL,
    source_branch                       VARCHAR(10) NOT NULL,
    source_account_number               VARCHAR(20) NOT NULL,
    source_account_opening_date         TIMESTAMPTZ NOT NULL,
    destination_participant_ispb        CHAR(8) NOT NULL,
    destination_branch                  VARCHAR(10) NOT NULL,
    destination_account_number          VARCHAR(20) NOT NULL,
    destination_account_opening_date    TIMESTAMPTZ NOT NULL,
    destination_document_number         VARCHAR(14) NOT NULL,
    destination_person_type             VARCHAR(10) NOT NULL,
    source_device_id                    VARCHAR(100) NOT NULL,
    source_channel                      VARCHAR(30) NOT NULL,
    source_ip                           INET NOT NULL,
    source_latitude                     NUMERIC(8,6),
    source_longitude                    NUMERIC(9,6),
    decision_id                         INTEGER NOT NULL REFERENCES decision(id),
    risk_score                          INTEGER,
    destination_risk_score              INTEGER,
    risk_policy_version_id              INTEGER NOT NULL REFERENCES risk_policy_version(id),
    two_factor_expires_at               TIMESTAMPTZ,
    created_at                          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(analysis_key),
    UNIQUE(pix_id),
    CONSTRAINT ck_pix_analysis_amount CHECK (amount_cents > 0),
    CONSTRAINT ck_pix_analysis_utc_offset CHECK (transaction_utc_offset_minutes BETWEEN -720 AND 840),
    CONSTRAINT ck_pix_analysis_source_document_number CHECK (source_document_number ~ '^([0-9]{11}|[0-9A-Z]{12}[0-9]{2})$'),
    CONSTRAINT ck_pix_analysis_destination_document_number CHECK (destination_document_number ~ '^([0-9]{11}|[0-9A-Z]{12}[0-9]{2})$'),
    CONSTRAINT ck_pix_analysis_source_person_type CHECK (source_person_type IN ('individual', 'company')),
    CONSTRAINT ck_pix_analysis_destination_person_type CHECK (destination_person_type IN ('individual', 'company')),
    CONSTRAINT ck_pix_analysis_source_person_type_matches_document_number CHECK ((source_person_type = 'individual') = (char_length(source_document_number) = 11)),
    CONSTRAINT ck_pix_analysis_destination_person_type_matches_document_number CHECK ((destination_person_type = 'individual') = (char_length(destination_document_number) = 11)),
    CONSTRAINT ck_pix_analysis_destination_participant_ispb CHECK (destination_participant_ispb ~ '^[0-9]{8}$'),
    CONSTRAINT ck_pix_analysis_branches CHECK (source_branch ~ '^[0-9]{1,10}$' AND destination_branch ~ '^[0-9]{1,10}$'),
    CONSTRAINT ck_pix_analysis_account_numbers CHECK (source_account_number ~ '^[0-9]{1,20}$' AND destination_account_number ~ '^[0-9]{1,20}$'),
    CONSTRAINT ck_pix_analysis_opening_dates CHECK (source_account_opening_date <= transaction_date AND destination_account_opening_date <= transaction_date),
    CONSTRAINT ck_pix_analysis_source_channel CHECK (source_channel ~ '^[a-z][a-z0-9_]{0,29}$'),
    CONSTRAINT ck_pix_analysis_source_latitude CHECK (source_latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_pix_analysis_source_longitude CHECK (source_longitude BETWEEN -180 AND 180),
    CONSTRAINT ck_pix_analysis_geolocation_complete CHECK ((source_latitude IS NULL) = (source_longitude IS NULL)),
    CONSTRAINT ck_pix_analysis_risk_score CHECK (risk_score >= 0),
    CONSTRAINT ck_pix_analysis_destination_risk_score CHECK (destination_risk_score >= 0),
    CONSTRAINT ck_pix_analysis_scores_together CHECK ((risk_score IS NULL) = (destination_risk_score IS NULL)),
    CONSTRAINT ck_pix_analysis_two_factor_expiration CHECK (two_factor_expires_at > transaction_date)
);

CREATE INDEX ix_pix_analysis_source_document_number ON pix_analysis(source_document_number, transaction_date);
CREATE INDEX ix_pix_analysis_destination_document_number ON pix_analysis(destination_document_number, transaction_date);
CREATE INDEX ix_pix_analysis_source_device ON pix_analysis(source_device_id, transaction_date);
CREATE INDEX ix_pix_analysis_person_type_pair ON pix_analysis(source_person_type, destination_person_type, transaction_date);

CREATE TABLE pix_analysis_rule_hit(
    id                              BIGSERIAL PRIMARY KEY,
    pix_analysis_id                 BIGINT NOT NULL REFERENCES pix_analysis(id),
    rule_id                         INTEGER NOT NULL REFERENCES rule(id),
    points                          INTEGER NOT NULL,
    reason                          VARCHAR(255) NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pix_analysis_id, rule_id),
    CONSTRAINT ck_pix_analysis_rule_hit_reason CHECK (char_length(btrim(reason)) > 0)
);

CREATE INDEX ix_pix_analysis_rule_hit_rule ON pix_analysis_rule_hit(rule_id, pix_analysis_id);

CREATE TABLE two_factor_confirmation(
    id                              BIGSERIAL PRIMARY KEY,
    pix_analysis_id                 BIGINT NOT NULL REFERENCES pix_analysis(id),
    result                          VARCHAR(10) NOT NULL,
    answered_at                     TIMESTAMPTZ NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pix_analysis_id),
    CONSTRAINT ck_two_factor_confirmation_result CHECK (result IN ('confirmed', 'denied'))
);

CREATE TABLE registered_device(
    id                              BIGSERIAL PRIMARY KEY,
    source_document_number          VARCHAR(14) NOT NULL,
    device_id                       VARCHAR(100) NOT NULL,
    registration_origin             VARCHAR(15) NOT NULL,
    registered_at                   TIMESTAMPTZ NOT NULL,
    registration_pix_analysis_id    BIGINT NOT NULL REFERENCES pix_analysis(id),
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_document_number, device_id),
    CONSTRAINT ck_registered_device_origin CHECK (registration_origin IN ('two_factor', 'first_seen'))
);

CREATE TABLE source_nightly_limit(
    id                              BIGSERIAL PRIMARY KEY,
    source_document_number          VARCHAR(14) NOT NULL,
    nightly_limit_cents             BIGINT NOT NULL,
    requested_at                    TIMESTAMPTZ NOT NULL,
    effective_at                    TIMESTAMPTZ NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_source_nightly_limit_individual_only CHECK (source_document_number ~ '^[0-9]{11}$'),
    CONSTRAINT ck_source_nightly_limit_amount CHECK (nightly_limit_cents > 0),
    CONSTRAINT ck_source_nightly_limit_effective_after_request CHECK (effective_at >= requested_at)
);

CREATE INDEX ix_source_nightly_limit_source_document_number ON source_nightly_limit(source_document_number, effective_at);

CREATE VIEW accepted_pix AS
SELECT
    pix_analysis.*,
    CASE WHEN decision.enumerator = 'approved' THEN 'direct' ELSE 'two_factor' END AS acceptance_path
FROM pix_analysis
JOIN decision ON decision.id = pix_analysis.decision_id
LEFT JOIN two_factor_confirmation ON two_factor_confirmation.pix_analysis_id = pix_analysis.id
WHERE decision.enumerator = 'approved'
   OR (decision.enumerator = 'two_factor_required' AND two_factor_confirmation.result = 'confirmed');

CREATE FUNCTION refuse_non_insert_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'A tabela % aceita apenas INSERT', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    insert_only_table TEXT;
BEGIN
    FOREACH insert_only_table IN ARRAY ARRAY[
        'decision',
        'rule',
        'risk_policy',
        'risk_policy_version',
        'risk_policy_rule_setting',
        'risk_policy_guardrail',
        'pix_analysis',
        'pix_analysis_rule_hit',
        'two_factor_confirmation',
        'registered_device',
        'source_nightly_limit'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER tr_%1$s_refuse_update_delete BEFORE UPDATE OR DELETE ON %1$I FOR EACH ROW EXECUTE FUNCTION refuse_non_insert_change()',
            insert_only_table
        );
        EXECUTE format(
            'CREATE TRIGGER tr_%1$s_refuse_truncate BEFORE TRUNCATE ON %1$I FOR EACH STATEMENT EXECUTE FUNCTION refuse_non_insert_change()',
            insert_only_table
        );
    END LOOP;
END;
$$;

INSERT INTO decision (enumerator) VALUES
('approved'),
('two_factor_required'),
('rejected');

INSERT INTO rule (code, kind, family, counterparty_signal, forced_decision_id, threshold_unit, uses_window_minutes, uses_company_threshold, description)
SELECT
    catalog.code,
    catalog.kind,
    catalog.family,
    catalog.counterparty_signal,
    decision.id,
    catalog.threshold_unit,
    catalog.uses_window_minutes,
    catalog.uses_company_threshold,
    catalog.description
FROM (VALUES
    ('device_used_by_many_sources', 'eliminatory', NULL, NULL, 'rejected', 'count', true, false, 'Mesmo aparelho usado por muitos pagadores PF diferentes em pouco tempo.'),
    ('impossible_travel_on_unregistered_device', 'eliminatory', NULL, NULL, 'rejected', 'km_per_hour', false, false, 'Viagem impossível desde o último Pix aceito, num dispositivo não cadastrado.'),
    ('new_account_to_new_destination_far_above_cap', 'eliminatory', NULL, NULL, 'rejected', 'multiplier', false, false, 'Conta nova pagando um destino novo muito acima do teto de conta nova.'),
    ('nightly_limit_exceeded', 'regulatory', NULL, NULL, 'rejected', NULL, false, false, 'Soma da noite entre PF acima do limite noturno, no horário local do Pix.'),
    ('unregistered_device_limit_exceeded', 'regulatory', NULL, NULL, 'two_factor_required', NULL, false, false, 'Aparelho não cadastrado acima dos limites da Res. BCB 403: R$ 200 por Pix ou R$ 1.000 por dia.'),
    ('impossible_travel', 'scoring', 'identity', NULL, NULL, 'km_per_hour', false, false, 'Pix a mais de 50 km do último Pix aceito do pagador, num deslocamento que exigiria mais de 900 km/h.'),
    ('ip_unfamiliar', 'scoring', 'identity', NULL, NULL, 'credibility_weight', false, false, 'IP nunca usado nos Pix aceitos do pagador. Pesa mais quanto maior o histórico.'),
    ('location_unfamiliar', 'scoring', 'identity', NULL, NULL, 'credibility_weight', false, false, 'Local nunca usado nos Pix aceitos do pagador. Pesa mais quanto maior o histórico.'),
    ('channel_unfamiliar', 'scoring', 'identity', NULL, NULL, 'credibility_weight', false, false, 'Canal nunca usado nos Pix aceitos do pagador. Pesa mais quanto maior o histórico.'),
    ('two_factor_denied_recently', 'scoring', 'identity', NULL, NULL, NULL, true, false, 'O pagador recusou um 2FA há pouco tempo.'),
    ('new_account_above_cap', 'scoring', 'velocity', NULL, NULL, NULL, false, false, 'Conta de origem nova pagando acima do teto de conta nova.'),
    ('burst_of_pix', 'scoring', 'velocity', NULL, NULL, 'count', true, true, 'Muitos Pix do mesmo pagador em poucos minutos. Pagador PJ tem limite próprio, porque paga em lote.'),
    ('amount_above_baseline', 'scoring', 'amount', NULL, NULL, 'multiplier', false, false, 'Pix acima do multiplicador vezes a base de comparação do par pagador e recebedor.'),
    ('amount_far_above_baseline', 'scoring', 'amount', NULL, NULL, 'multiplier', false, false, 'Pix muito acima da base de comparação do par pagador e recebedor. Exclusiva com o valor fora do padrão: dispara só a mais grave.'),
    ('monthly_volume_above_typical', 'scoring', 'amount', NULL, NULL, 'multiplier', true, false, 'Volume do mês acima do volume mensal típico do pagador.'),
    ('destination_account_opened_very_recently', 'scoring', 'counterparty', 'relationship', NULL, 'days', false, false, 'Conta de destino aberta há muito pouco tempo.'),
    ('destination_account_opened_recently', 'scoring', 'counterparty', 'relationship', NULL, 'days', false, false, 'Conta de destino aberta há poucos dias.'),
    ('new_destination_above_usual_ceiling', 'scoring', 'counterparty', 'relationship', NULL, 'multiplier', false, true, 'Destino novo recebendo acima de um múltiplo do teto habitual do pagador, a partir do piso das regras de valor. Recebedor PJ tem múltiplo próprio, para a primeira compra numa loja não parecer golpe.'),
    ('destination_receiving_from_many_sources', 'scoring', 'counterparty', 'base', NULL, 'count', true, false, 'Recebedor PF recebendo, a partir do piso das regras de valor, de muitos pagadores diferentes em pouco tempo.'),
    ('destination_rejected_for_other_sources', 'scoring', 'counterparty', 'base', NULL, 'count', true, false, 'Recebedor com 2FA recusados, ou Pix reprovados com regra de contraparte, de outros pagadores.'),
    ('destination_document_in_many_accounts', 'scoring', 'counterparty', 'base', NULL, 'count', true, true, 'Mesmo documento de recebedor recebendo em várias contas de destino diferentes.'),
    ('same_owner', 'reducer', NULL, NULL, NULL, NULL, false, false, 'Documento do pagador igual ao do recebedor.'),
    ('known_destination', 'reducer', NULL, NULL, NULL, 'count', false, false, 'Recebedor com vários Pix aceitos do pagador.'),
    ('long_registered_device', 'reducer', NULL, NULL, NULL, 'days', false, false, 'Dispositivo cadastrado há muito tempo.')
) AS catalog(code, kind, family, counterparty_signal, forced_decision, threshold_unit, uses_window_minutes, uses_company_threshold, description)
LEFT JOIN decision ON decision.enumerator = catalog.forced_decision;

INSERT INTO risk_policy (name, kind) VALUES
('conservative', 'template'),
('balanced', 'template'),
('permissive', 'template'),
('bank', 'bank');

INSERT INTO risk_policy_version (
    risk_policy_id,
    version_number,
    based_on_version_id,
    change_reason,
    history_window_days,
    source_baseline_reference_weight,
    population_median_reference_weight,
    reference_average_ticket_individual_to_individual_cents,
    reference_average_ticket_individual_to_company_cents,
    reference_average_ticket_company_to_individual_cents,
    reference_average_ticket_company_to_company_cents,
    amount_rules_floor_cents,
    new_account_age_days,
    new_account_cap_individual_cents,
    new_account_cap_company_cents,
    identity_family_cap,
    velocity_family_cap,
    amount_family_cap,
    counterparty_family_cap,
    counterparty_relationship_cap,
    behavior_score_cap,
    two_factor_score_threshold,
    rejection_score_threshold,
    two_factor_validity_minutes,
    destination_risk_alert_threshold,
    short_term_window_minutes
)
SELECT
    risk_policy.id,
    1,
    NULL,
    template.change_reason,
    90, 5, 30,
    26864, 11242, 54958, 540453,
    10000,
    30, 100000, 1000000,
    50, 40, 35, 70,
    30,
    template.behavior_score_cap,
    template.two_factor_score_threshold,
    template.rejection_score_threshold,
    10,
    template.destination_risk_alert_threshold,
    1440
FROM (VALUES
    ('conservative', 'Modelo conservador', 105, 35, 60, 25),
    ('balanced', 'Modelo equilibrado', 65, 40, 70, 30),
    ('permissive', 'Modelo permissivo', 75, 45, 80, 30)
) AS template(name, change_reason, behavior_score_cap, two_factor_score_threshold, rejection_score_threshold, destination_risk_alert_threshold)
JOIN risk_policy ON risk_policy.name = template.name;

INSERT INTO risk_policy_version (
    risk_policy_id,
    version_number,
    based_on_version_id,
    change_reason,
    history_window_days,
    source_baseline_reference_weight,
    population_median_reference_weight,
    reference_average_ticket_individual_to_individual_cents,
    reference_average_ticket_individual_to_company_cents,
    reference_average_ticket_company_to_individual_cents,
    reference_average_ticket_company_to_company_cents,
    amount_rules_floor_cents,
    new_account_age_days,
    new_account_cap_individual_cents,
    new_account_cap_company_cents,
    identity_family_cap,
    velocity_family_cap,
    amount_family_cap,
    counterparty_family_cap,
    counterparty_relationship_cap,
    behavior_score_cap,
    two_factor_score_threshold,
    rejection_score_threshold,
    two_factor_validity_minutes,
    destination_risk_alert_threshold,
    short_term_window_minutes
)
SELECT
    bank_policy.id,
    1,
    balanced_version.id,
    'Versão inicial, copiada do modelo equilibrado',
    balanced_version.history_window_days,
    balanced_version.source_baseline_reference_weight,
    balanced_version.population_median_reference_weight,
    balanced_version.reference_average_ticket_individual_to_individual_cents,
    balanced_version.reference_average_ticket_individual_to_company_cents,
    balanced_version.reference_average_ticket_company_to_individual_cents,
    balanced_version.reference_average_ticket_company_to_company_cents,
    balanced_version.amount_rules_floor_cents,
    balanced_version.new_account_age_days,
    balanced_version.new_account_cap_individual_cents,
    balanced_version.new_account_cap_company_cents,
    balanced_version.identity_family_cap,
    balanced_version.velocity_family_cap,
    balanced_version.amount_family_cap,
    balanced_version.counterparty_family_cap,
    balanced_version.counterparty_relationship_cap,
    balanced_version.behavior_score_cap,
    balanced_version.two_factor_score_threshold,
    balanced_version.rejection_score_threshold,
    balanced_version.two_factor_validity_minutes,
    balanced_version.destination_risk_alert_threshold,
    balanced_version.short_term_window_minutes
FROM risk_policy AS bank_policy
JOIN risk_policy AS balanced_policy ON balanced_policy.name = 'balanced'
JOIN risk_policy_version AS balanced_version ON balanced_version.risk_policy_id = balanced_policy.id AND balanced_version.version_number = 1
WHERE bank_policy.name = 'bank';

INSERT INTO risk_policy_guardrail (policy_parameter_name, loosening_direction, loosest_accepted_value) VALUES
('two_factor_score_threshold', 'higher', 45),
('rejection_score_threshold', 'higher', 80),
('destination_risk_alert_threshold', 'higher', 30),
('amount_rules_floor_cents', 'higher', 500000),
('new_account_age_days', 'lower', 15),
('new_account_cap_individual_cents', 'higher', 200000),
('new_account_cap_company_cents', 'higher', 2000000),
('short_term_window_minutes', 'lower', 720),
('identity_family_cap', 'lower', NULL),
('velocity_family_cap', 'lower', NULL),
('amount_family_cap', 'lower', NULL),
('counterparty_family_cap', 'lower', NULL),
('counterparty_relationship_cap', 'lower', NULL),
('behavior_score_cap', 'lower', NULL);

INSERT INTO risk_policy_guardrail (rule_id, rule_setting_field, loosening_direction, loosest_accepted_value)
SELECT rule.id, 'points', 'lower', NULL
FROM rule
WHERE rule.kind IN ('scoring', 'reducer');

INSERT INTO risk_policy_guardrail (rule_id, rule_setting_field, loosening_direction, loosest_accepted_value)
SELECT rule.id, limit_row.rule_setting_field, limit_row.loosening_direction, limit_row.loosest_accepted_value
FROM (VALUES
    ('device_used_by_many_sources', 'threshold', 'higher', 8::NUMERIC),
    ('impossible_travel_on_unregistered_device', 'threshold', 'higher', 1200),
    ('new_account_to_new_destination_far_above_cap', 'threshold', 'higher', 10),
    ('impossible_travel', 'threshold', 'higher', 1200),
    ('ip_unfamiliar', 'threshold', 'higher', 10),
    ('location_unfamiliar', 'threshold', 'higher', 10),
    ('channel_unfamiliar', 'threshold', 'higher', 10),
    ('burst_of_pix', 'threshold', 'higher', 10),
    ('burst_of_pix', 'company_threshold', 'higher', 100),
    ('amount_above_baseline', 'threshold', 'higher', 10),
    ('amount_far_above_baseline', 'threshold', 'higher', 40),
    ('monthly_volume_above_typical', 'threshold', 'higher', 6),
    ('destination_account_opened_very_recently', 'threshold', 'lower', 3),
    ('destination_account_opened_recently', 'threshold', 'lower', 15),
    ('new_destination_above_usual_ceiling', 'threshold', 'higher', 2),
    ('new_destination_above_usual_ceiling', 'company_threshold', 'higher', 5),
    ('destination_receiving_from_many_sources', 'threshold', 'higher', 8),
    ('destination_rejected_for_other_sources', 'threshold', 'higher', 3),
    ('destination_document_in_many_accounts', 'threshold', 'higher', 5),
    ('destination_document_in_many_accounts', 'company_threshold', 'higher', 15),
    ('known_destination', 'threshold', 'lower', 2),
    ('long_registered_device', 'threshold', 'lower', 15)
) AS limit_row(rule_code, rule_setting_field, loosening_direction, loosest_accepted_value)
JOIN rule ON rule.code = limit_row.rule_code;

INSERT INTO risk_policy_rule_setting (risk_policy_version_id, rule_id, enabled, points, threshold, window_minutes, company_threshold)
SELECT
    risk_policy_version.id,
    rule.id,
    true,
    setting.points,
    CASE rule.code
        WHEN 'amount_above_baseline' THEN policy_multiplier.amount_above_baseline_multiplier
        WHEN 'amount_far_above_baseline' THEN policy_multiplier.amount_far_above_baseline_multiplier
        ELSE setting.threshold
    END,
    setting.window_minutes,
    setting.company_threshold
FROM (VALUES
    ('device_used_by_many_sources', NULL::INTEGER, 5::NUMERIC, 1440, NULL::NUMERIC),
    ('impossible_travel_on_unregistered_device', NULL, 900, NULL, NULL),
    ('new_account_to_new_destination_far_above_cap', NULL, 5, NULL, NULL),
    ('impossible_travel', 40, 900, NULL, NULL),
    ('ip_unfamiliar', 10, 5, NULL, NULL),
    ('location_unfamiliar', 10, 5, NULL, NULL),
    ('channel_unfamiliar', 15, 5, NULL, NULL),
    ('two_factor_denied_recently', 30, NULL, 1440, NULL),
    ('new_account_above_cap', 40, NULL, NULL, NULL),
    ('burst_of_pix', 25, 5, 5, 50),
    ('amount_above_baseline', 25, NULL, NULL, NULL),
    ('amount_far_above_baseline', 35, NULL, NULL, NULL),
    ('monthly_volume_above_typical', 20, 3, 43200, NULL),
    ('destination_account_opened_very_recently', 25, 7, NULL, NULL),
    ('destination_account_opened_recently', 20, 30, NULL, NULL),
    ('new_destination_above_usual_ceiling', 30, 1, NULL, 3),
    ('destination_receiving_from_many_sources', 30, 5, 60, NULL),
    ('destination_rejected_for_other_sources', 20, 2, 10080, NULL),
    ('destination_document_in_many_accounts', 30, 3, 1440, 10),
    ('same_owner', -30, NULL, NULL, NULL),
    ('known_destination', -20, 3, NULL, NULL),
    ('long_registered_device', -10, 30, NULL, NULL)
) AS setting(code, points, threshold, window_minutes, company_threshold)
JOIN rule ON rule.code = setting.code
CROSS JOIN risk_policy_version
JOIN risk_policy ON risk_policy.id = risk_policy_version.risk_policy_id
JOIN (VALUES
    ('conservative', 3::NUMERIC, 10::NUMERIC),
    ('balanced', 5::NUMERIC, 20::NUMERIC),
    ('permissive', 10::NUMERIC, 40::NUMERIC),
    ('bank', 5::NUMERIC, 20::NUMERIC)
) AS policy_multiplier(policy_name, amount_above_baseline_multiplier, amount_far_above_baseline_multiplier) ON policy_multiplier.policy_name = risk_policy.name;
