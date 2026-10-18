import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from tests.utils.assertions import rule_codes
from tests.utils.clock import business_hours_today, iso
from tests.utils.pix_payload import (
    DEFAULT_AMOUNT_CENTS,
    Payee,
    Payer,
    new_company_payee,
    new_individual_payee,
    new_individual_payer,
    pix_payload,
)
from tests.utils.request_generator import RequestGenerator


NEW_ACCOUNT_AGE = timedelta(days=10)
NEW_ACCOUNT_TWO_FACTOR_AMOUNT_CENTS = 150000
NIGHTLY_LIMIT_BREAKING_AMOUNT_CENTS = 150000
FAR_ABOVE_NEW_ACCOUNT_CAP_AMOUNT_CENTS = 500001
HISTORY_SPACING = timedelta(days=1)
RESTORE_BALANCED_POLICY = {
    "change_reason": "Restaura o modelo equilibrado depois de um teste que editou a política",
    "based_on_template": "balanced",
}


def setup_ok(status: int, body, step: str, expected_statuses=(200, 201)):
    assert status in expected_statuses, f"A preparação do cenário falhou em '{step}': HTTP {status} {body}"
    return body


def analyze(payload: dict, step: str = "enviar o Pix") -> dict:
    status, body = RequestGenerator.POST_pix_transaction(payload)
    return setup_ok(status, body, step, expected_statuses=(201,))


def analyze_expecting(payload: dict, decision: str, step: str) -> dict:
    analysis = analyze(payload, step)
    assert analysis["status"] == decision, (
        f"A preparação do cenário falhou em '{step}': esperava {decision} e veio {analysis['status']} "
        f"com as regras {sorted(rule_codes(analysis))}"
    )
    return analysis


def build_accepted_history(
    payer: Payer,
    payee: Payee,
    last_transaction_date: datetime,
    count: int,
    amount_cents: int = DEFAULT_AMOUNT_CENTS,
    spacing: timedelta = HISTORY_SPACING,
    **pix_overrides,
) -> list:
    analyses = []
    for position in range(count):
        transaction_date = last_transaction_date - spacing * (count - 1 - position)
        payload = pix_payload(payer, payee, transaction_date, amount_cents, **pix_overrides)
        analyses.append(analyze_expecting(payload, "approved", f"montar o histórico aceito ({position + 1} de {count})"))
    return analyses


def payer_with_accepted_history(
    last_transaction_date: datetime,
    count: int,
    amount_cents: int = DEFAULT_AMOUNT_CENTS,
    payee: Payee = None,
    payer: Payer = None,
    **pix_overrides,
) -> tuple:
    payer = payer or new_individual_payer()
    payee = payee or new_individual_payee()
    analyses = build_accepted_history(payer, payee, last_transaction_date, count, amount_cents, **pix_overrides)
    return payer, payee, analyses


def payer_with_registered_device(payee: Payee = None) -> tuple:
    first_pix_date = business_hours_today() - timedelta(days=10)
    payer, payee, _ = payer_with_accepted_history(first_pix_date, 1, payee=payee)
    analyze_expecting(
        pix_payload(payer, payee, first_pix_date + timedelta(days=1), 100000),
        "approved",
        "subir o teto habitual do pagador para R$ 1.000 no aparelho cadastrado",
    )
    return payer, payee


def new_account_payer(transaction_date: datetime) -> Payer:
    return new_individual_payer(opening_date=transaction_date - NEW_ACCOUNT_AGE)


def two_factor_pix(transaction_date: datetime, payer: Payer = None, payee: Payee = None) -> tuple:
    payer = payer or new_account_payer(transaction_date)
    payee = payee or new_company_payee()
    payload = pix_payload(payer, payee, transaction_date, NEW_ACCOUNT_TWO_FACTOR_AMOUNT_CENTS)
    analysis = analyze_expecting(payload, "two_factor_required", "levar um Pix de conta nova ao 2FA")
    return payer, payee, payload, analysis


def confirm_two_factor(pix_id: str, result: str, confirmed_at: datetime) -> dict:
    status, body = RequestGenerator.POST_two_factor_confirmation(
        pix_id,
        {"result": result, "confirmed_at": iso(confirmed_at)},
    )
    return setup_ok(status, body, f"informar o 2FA como {result}", expected_statuses=(201,))


def nightly_rejected_pix(payee: Payee, transaction_date: datetime, payer: Payer = None) -> dict:
    payer = payer or new_individual_payer()
    payload = pix_payload(payer, payee, transaction_date, NIGHTLY_LIMIT_BREAKING_AMOUNT_CENTS)
    return analyze_expecting(payload, "rejected", "estourar o limite noturno")


def counterparty_rejected_pix(payee: Payee, transaction_date: datetime, payer: Payer = None) -> dict:
    payer = payer or new_account_payer(transaction_date)
    payload = pix_payload(payer, payee, transaction_date, FAR_ABOVE_NEW_ACCOUNT_CAP_AMOUNT_CENTS)
    return analyze_expecting(payload, "rejected", "conta nova pagando destino novo muito acima do teto")


def fire_together(calls: list) -> list:
    start_line = threading.Barrier(len(calls))

    def wait_and_call(call):
        start_line.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        return list(executor.map(wait_and_call, calls))


def edit_bank_policy(payload: dict, step: str) -> dict:
    status, body = RequestGenerator.POST_risk_policy_version(payload)
    return setup_ok(status, body, step, expected_statuses=(201,))


def current_bank_policy() -> dict:
    status, body = RequestGenerator.GET_risk_policy()
    return setup_ok(status, body, "ler a política vigente", expected_statuses=(200,))


def restore_balanced_bank_policy() -> None:
    status, body = RequestGenerator.POST_risk_policy_version(RESTORE_BALANCED_POLICY)
    assert status == 201, f"A política não voltou ao modelo equilibrado e o resto da suíte rodaria com a política errada: HTTP {status} {body}"
