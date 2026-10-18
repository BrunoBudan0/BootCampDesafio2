from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Optional

from tests.utils.clock import iso, now_in_sao_paulo
from tests.utils.random_generator import RandomGenerator


DEFAULT_AMOUNT_CENTS = 10000
DEFAULT_CHANNEL = "app"
ESTABLISHED_ACCOUNT_AGE = timedelta(days=730)
DESTINATION_PARTICIPANT = "60701190"

SAO_PAULO_LOCATION = (-23.5505, -46.6333)
SAO_PAULO_NEARBY_LOCATION = (-23.5512, -46.6341)
RIO_DE_JANEIRO_LOCATION = (-22.9068, -43.1729)
MANAUS_LOCATION = (-3.1190, -60.0217)
CAMPINAS_LOCATION = (-22.9099, -47.0626)


@dataclass(frozen=True)
class Payer:
    document_number: str
    branch: str
    account_number: str
    opening_date: datetime
    device_id: str
    channel: str
    ip: str


@dataclass(frozen=True)
class Payee:
    document_number: str
    participant: str
    branch: str
    account_number: str
    opening_date: datetime


def established_opening_date() -> datetime:
    return now_in_sao_paulo() - ESTABLISHED_ACCOUNT_AGE


def new_payer(document_number: str, opening_date: Optional[datetime]) -> Payer:
    return Payer(
        document_number=document_number,
        branch=RandomGenerator.generate_branch(),
        account_number=RandomGenerator.generate_account_number(),
        opening_date=opening_date or established_opening_date(),
        device_id=RandomGenerator.generate_device_id(),
        channel=DEFAULT_CHANNEL,
        ip=RandomGenerator.generate_ip(),
    )


def new_payee(document_number: str, opening_date: Optional[datetime]) -> Payee:
    return Payee(
        document_number=document_number,
        participant=DESTINATION_PARTICIPANT,
        branch=RandomGenerator.generate_branch(),
        account_number=RandomGenerator.generate_account_number(),
        opening_date=opening_date or established_opening_date(),
    )


def new_individual_payer(opening_date: Optional[datetime] = None) -> Payer:
    return new_payer(RandomGenerator.generate_cpf(), opening_date)


def new_company_payer(opening_date: Optional[datetime] = None) -> Payer:
    return new_payer(RandomGenerator.generate_cnpj(), opening_date)


def new_individual_payee(opening_date: Optional[datetime] = None) -> Payee:
    return new_payee(RandomGenerator.generate_cpf(), opening_date)


def new_company_payee(opening_date: Optional[datetime] = None) -> Payee:
    return new_payee(RandomGenerator.generate_cnpj(), opening_date)


def payee_owned_by(payer: Payer, opening_date: Optional[datetime] = None) -> Payee:
    return new_payee(payer.document_number, opening_date)


def same_payee_in_another_account(payee: Payee) -> Payee:
    return replace(
        payee,
        branch=RandomGenerator.generate_branch(),
        account_number=RandomGenerator.generate_account_number(),
    )


def payer_on_another_device(payer: Payer) -> Payer:
    return replace(payer, device_id=RandomGenerator.generate_device_id())


def pix_payload(
    payer: Payer,
    payee: Payee,
    transaction_date: datetime,
    amount_cents: int = DEFAULT_AMOUNT_CENTS,
    device_id: Optional[str] = None,
    channel: Optional[str] = None,
    ip: Optional[str] = None,
    location: Optional[tuple] = None,
    pix_id: Optional[str] = None,
) -> dict:
    source = {
        "device_id": device_id or payer.device_id,
        "channel": channel or payer.channel,
        "ip": ip or payer.ip,
    }
    if location is not None:
        source["geolocation"] = {"latitude": location[0], "longitude": location[1]}

    return {
        "id": pix_id or RandomGenerator.generate_pix_id(),
        "amount": amount_cents,
        "transaction_date": iso(transaction_date),
        "source_account": {
            "branch": payer.branch,
            "account_number": payer.account_number,
            "opening_date": iso(payer.opening_date),
            "owner": {"document_number": payer.document_number},
        },
        "destination_account": {
            "participant": payee.participant,
            "branch": payee.branch,
            "account_number": payee.account_number,
            "opening_date": iso(payee.opening_date),
            "owner": {"document_number": payee.document_number},
        },
        "source": source,
    }
