import hashlib
import ipaddress
import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from errors import AccountOpenedAfterTransaction, InvalidDate, InvalidDocumentNumber, InvalidIpAddress, InvalidSchema
from utils.document_number import is_valid_document_number, normalized_document_number, person_type_of
from utils.iso_datetime import parsed_datetime_with_offset, utc_offset_minutes


@dataclass(frozen=True)
class PixUnderAnalysis:
    pix_id: str
    payload_hash: str
    amount_cents: int
    transaction_date: datetime
    transaction_utc_offset_minutes: int
    source_document: str
    source_person_type: str
    source_branch: str
    source_account_number: str
    source_account_opening_date: datetime
    destination_participant: str
    destination_branch: str
    destination_account_number: str
    destination_account_opening_date: datetime
    destination_document: str
    destination_person_type: str
    device_id: str
    channel: str
    ip: str
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]

    @property
    def has_geolocation(self) -> bool:
        return self.latitude is not None


def required_datetime(text: str, field_name: str) -> datetime:
    moment = parsed_datetime_with_offset(text)

    if moment is None:
        raise InvalidDate(field_name)

    return moment


def required_document(document_number: str, field_name: str) -> str:
    if not is_valid_document_number(document_number):
        raise InvalidDocumentNumber(field_name)

    return normalized_document_number(document_number)


def required_ip(ip_text: str) -> str:
    try:
        return str(ipaddress.ip_address(ip_text))
    except ValueError:
        raise InvalidIpAddress()


def finite_coordinate(value, field_name: str) -> Decimal:
    if not math.isfinite(value):
        raise InvalidSchema(f"{field_name} must be a finite number")

    return Decimal(str(value))


def normalized_payload(payload: dict, source_document: str, destination_document: str) -> dict:
    normalized = json.loads(json.dumps(payload))
    normalized["amount"] = int(payload["amount"])
    normalized["source_account"]["owner"]["document_number"] = source_document
    normalized["destination_account"]["owner"]["document_number"] = destination_document
    normalized["source"]["channel"] = payload["source"]["channel"].lower()
    if normalized["source"].get("geolocation") is None:
        normalized["source"].pop("geolocation", None)
    return normalized


def payload_hash_of(normalized: dict) -> str:
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def pix_under_analysis_from(payload: dict) -> PixUnderAnalysis:
    source_account = payload["source_account"]
    destination_account = payload["destination_account"]
    source = payload["source"]
    geolocation = source.get("geolocation")

    latitude = None
    longitude = None
    if geolocation is not None:
        latitude = finite_coordinate(geolocation["latitude"], "source.geolocation.latitude")
        longitude = finite_coordinate(geolocation["longitude"], "source.geolocation.longitude")

    transaction_date = required_datetime(payload["transaction_date"], "transaction_date")
    source_account_opening_date = required_datetime(source_account["opening_date"], "source_account.opening_date")
    destination_account_opening_date = required_datetime(destination_account["opening_date"], "destination_account.opening_date")
    source_document = required_document(source_account["owner"]["document_number"], "source_account.owner.document_number")
    destination_document = required_document(
        destination_account["owner"]["document_number"], "destination_account.owner.document_number"
    )
    ip = required_ip(source["ip"])

    if source_account_opening_date > transaction_date:
        raise AccountOpenedAfterTransaction("source_account")

    if destination_account_opening_date > transaction_date:
        raise AccountOpenedAfterTransaction("destination_account")

    return PixUnderAnalysis(
        pix_id=payload["id"],
        payload_hash=payload_hash_of(normalized_payload(payload, source_document, destination_document)),
        amount_cents=int(payload["amount"]),
        transaction_date=transaction_date,
        transaction_utc_offset_minutes=utc_offset_minutes(transaction_date),
        source_document=source_document,
        source_person_type=person_type_of(source_document),
        source_branch=source_account["branch"],
        source_account_number=source_account["account_number"],
        source_account_opening_date=source_account_opening_date,
        destination_participant=destination_account["participant"],
        destination_branch=destination_account["branch"],
        destination_account_number=destination_account["account_number"],
        destination_account_opening_date=destination_account_opening_date,
        destination_document=destination_document,
        destination_person_type=person_type_of(destination_document),
        device_id=source["device_id"],
        channel=source["channel"].lower(),
        ip=ip,
        latitude=latitude,
        longitude=longitude,
    )
