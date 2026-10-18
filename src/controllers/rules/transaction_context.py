import ipaddress
import statistics
from datetime import datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import cached_property
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from controllers.rules.credibility import credibility_blend
from controllers.rules.pix_under_analysis import PixUnderAnalysis
from models import PixAnalysis, RiskPolicyVersion


EARTH_RADIUS_KM = 6371
IMPOSSIBLE_TRAVEL_MINIMUM_DISTANCE_KM = 50
LOCATION_PLACES = Decimal("0.01")
NIGHT_STARTS_AT = time(20)
NIGHT_ENDS_AT = time(6)
DEFAULT_NIGHTLY_LIMIT_CENTS = 100000
NIGHTLY_LIMIT_RAISE_DELAY = timedelta(hours=24)


def is_accepted(analysis: PixAnalysis) -> bool:
    decision = analysis.decision.enumerator
    confirmation = analysis.two_factor_confirmation
    return decision == "approved" or (
        decision == "two_factor_required" and confirmation is not None and confirmation.result == "confirmed"
    )


def is_same_owner(pix) -> bool:
    return pix.source_document == pix.destination_document


def is_pending_two_factor_at(analysis: PixAnalysis, moment: datetime) -> bool:
    return (
        analysis.decision.enumerator == "two_factor_required"
        and analysis.two_factor_confirmation is None
        and analysis.two_factor_expires_at > moment
    )


def rounded_location(latitude, longitude) -> tuple:
    return (
        Decimal(latitude).quantize(LOCATION_PLACES, rounding=ROUND_HALF_UP),
        Decimal(longitude).quantize(LOCATION_PLACES, rounding=ROUND_HALF_UP),
    )


def distance_km(first_latitude, first_longitude, second_latitude, second_longitude) -> float:
    lat1, lon1, lat2, lon2 = map(radians, map(float, (first_latitude, first_longitude, second_latitude, second_longitude)))
    haversine = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))


def nightly_limit_in_force(nightly_limits: list, moment: datetime) -> int:
    candidates = [nightly_limit for nightly_limit in nightly_limits if nightly_limit.requested_at <= moment]

    while candidates:
        latest = max(candidates, key=lambda nightly_limit: (nightly_limit.requested_at, nightly_limit.id or 0))
        if latest.effective_at <= moment:
            return latest.nightly_limit_cents
        candidates = [nightly_limit for nightly_limit in candidates if nightly_limit.requested_at < latest.requested_at]

    return DEFAULT_NIGHTLY_LIMIT_CENTS


def nightly_limit_effective_at(nightly_limits: list, requested_limit_cents: int, requested_at: datetime) -> datetime:
    if requested_limit_cents > nightly_limit_in_force(nightly_limits, requested_at):
        return requested_at + NIGHTLY_LIMIT_RAISE_DELAY

    return requested_at


class TransactionContext:
    def __init__(
        self,
        pix: PixUnderAnalysis,
        policy_version: RiskPolicyVersion,
        pix_analysis_repository,
        source_repository,
    ) -> None:
        self.pix = pix
        self.policy = policy_version
        self.settings = {setting.rule.code: setting for setting in policy_version.rule_settings}
        self.pix_analysis_repository = pix_analysis_repository
        self.source_repository = source_repository
        self.moment = pix.transaction_date

    def setting(self, rule_code: str):
        return self.settings[rule_code]

    def window_start(self, minutes) -> datetime:
        return self.moment - timedelta(minutes=float(minutes))

    @cached_property
    def lookback_minutes(self) -> float:
        payer_windows = [
            self.policy.history_window_days * 1440,
            self.policy.short_term_window_minutes,
            1440,
        ]
        payer_windows.extend(
            setting.window_minutes
            for setting in self.policy.rule_settings
            if setting.window_minutes is not None
        )
        return float(max(payer_windows))

    @cached_property
    def source_analyses(self) -> list:
        return self.pix_analysis_repository.find_source_analyses_between(
            self.pix.source_document, self.window_start(self.lookback_minutes), self.moment
        )

    @cached_property
    def history_start(self) -> datetime:
        return self.moment - timedelta(days=self.policy.history_window_days)

    @cached_property
    def accepted_history(self) -> list:
        return [
            analysis
            for analysis in self.source_analyses
            if analysis.transaction_date > self.history_start and is_accepted(analysis)
        ]

    @property
    def history_count(self) -> int:
        return len(self.accepted_history)

    @property
    def is_cold_start(self) -> bool:
        return self.history_count == 0

    @cached_property
    def limit_using_analyses(self) -> list:
        return [
            analysis
            for analysis in self.source_analyses
            if is_accepted(analysis) or is_pending_two_factor_at(analysis, self.moment)
        ]

    def limit_usage_since(self, since: datetime, inclusive: bool = False, **matching) -> int:
        used = 0
        for analysis in self.limit_using_analyses:
            in_window = analysis.transaction_date >= since if inclusive else analysis.transaction_date > since
            if in_window and all(getattr(analysis, field) == value for field, value in matching.items()):
                used += analysis.amount_cents
        return used

    @cached_property
    def accumulated_total_amount(self) -> int:
        return self.pix.amount_cents + self.limit_usage_since(self.window_start(self.policy.short_term_window_minutes))

    @cached_property
    def accumulated_amount_to_destination(self) -> int:
        return self.pix.amount_cents + self.limit_usage_since(
            self.window_start(self.policy.short_term_window_minutes),
            destination_document=self.pix.destination_document,
        )

    @cached_property
    def pair_history_amounts(self) -> list:
        return [
            analysis.amount_cents
            for analysis in self.accepted_history
            if analysis.source_person_type == self.pix.source_person_type
            and analysis.destination_person_type == self.pix.destination_person_type
            and not is_same_owner(analysis)
        ]

    @cached_property
    def reference_average_ticket_cents(self) -> int:
        pair_name = f"{self.pix.source_person_type}_to_{self.pix.destination_person_type}"
        return getattr(self.policy, f"reference_average_ticket_{pair_name}_cents")

    @cached_property
    def population_median_amount(self) -> Decimal:
        count, observed_median = self.pix_analysis_repository.population_accepted_amounts_summary(
            self.pix.source_person_type, self.pix.destination_person_type, self.history_start, self.moment
        )
        if count == 0:
            return Decimal(self.reference_average_ticket_cents)

        return credibility_blend(
            Decimal(str(observed_median)), count, self.reference_average_ticket_cents, self.policy.population_median_weight
        )

    @cached_property
    def baseline_amount(self) -> Decimal:
        if not self.pair_history_amounts:
            return self.population_median_amount

        return credibility_blend(
            Decimal(str(statistics.median(self.pair_history_amounts))),
            len(self.pair_history_amounts),
            self.population_median_amount,
            self.policy.source_history_weight,
        )

    @cached_property
    def usual_ceiling_amount(self) -> Decimal:
        amounts_to_other_owners = [
            Decimal(analysis.amount_cents)
            for analysis in self.accepted_history_before_short_term
            if not is_same_owner(analysis)
        ]
        return max([self.baseline_amount, *amounts_to_other_owners])

    @cached_property
    def accepted_history_before_short_term(self) -> list:
        short_term_start = self.window_start(self.policy.short_term_window_minutes)
        return [analysis for analysis in self.accepted_history if analysis.transaction_date <= short_term_start]

    @cached_property
    def known_destination_documents(self) -> set:
        return {analysis.destination_document for analysis in self.accepted_history_before_short_term}

    @property
    def is_new_destination(self) -> bool:
        return self.pix.destination_document not in self.known_destination_documents

    @cached_property
    def accepted_count_to_destination(self) -> int:
        return sum(
            1
            for analysis in self.accepted_history_before_short_term
            if analysis.destination_document == self.pix.destination_document
        )

    @property
    def is_new_account(self) -> bool:
        return self.moment - self.pix.source_account_opening_date < timedelta(days=self.policy.new_account_age_days)

    @property
    def new_account_cap_cents(self) -> int:
        if self.pix.source_person_type == "individual":
            return self.policy.new_account_cap_individual_cents

        return self.policy.new_account_cap_company_cents

    @property
    def destination_account_age(self) -> timedelta:
        return self.moment - self.pix.destination_account_opening_date

    @cached_property
    def registered_device(self):
        return self.source_repository.find_registered_device(self.pix.source_document, self.pix.device_id)

    @property
    def is_device_registered(self) -> bool:
        return self.registered_device is not None and self.registered_device.registered_at <= self.moment

    @cached_property
    def source_has_any_accepted_pix(self) -> bool:
        return self.pix_analysis_repository.source_has_any_accepted_pix(self.pix.source_document)

    @cached_property
    def last_located_accepted_pix(self) -> Optional[PixAnalysis]:
        located = [analysis for analysis in self.accepted_history if analysis.latitude is not None]
        return located[-1] if located else None

    @cached_property
    def travel_speed_kmh(self) -> Optional[float]:
        previous = self.last_located_accepted_pix

        if previous is None or not self.pix.has_geolocation:
            return None

        distance = distance_km(previous.latitude, previous.longitude, self.pix.latitude, self.pix.longitude)

        if distance < IMPOSSIBLE_TRAVEL_MINIMUM_DISTANCE_KM:
            return None

        hours = (self.moment - previous.transaction_date).total_seconds() / 3600

        if hours <= 0:
            return float("inf") if distance > 0 else 0.0

        return distance / hours

    @cached_property
    def local_time(self) -> datetime:
        return self.moment.astimezone(timezone(timedelta(minutes=self.pix.transaction_utc_offset_minutes)))

    @property
    def is_night(self) -> bool:
        local_clock = self.local_time.time()
        return local_clock >= NIGHT_STARTS_AT or local_clock < NIGHT_ENDS_AT

    @property
    def night_start(self) -> datetime:
        night_date = self.local_time.date()
        if self.local_time.time() < NIGHT_ENDS_AT:
            night_date -= timedelta(days=1)
        return datetime.combine(night_date, NIGHT_STARTS_AT, tzinfo=self.local_time.tzinfo)

    @property
    def local_day_start(self) -> datetime:
        return datetime.combine(self.local_time.date(), time(0), tzinfo=self.local_time.tzinfo)

    @cached_property
    def nightly_limit_cents(self) -> int:
        return nightly_limit_in_force(self.source_repository.find_nightly_limits(self.pix.source_document), self.moment)

    def is_value_never_seen(self, value_of) -> bool:
        return all(value_of(analysis) != value_of(self.pix) for analysis in self.accepted_history)

    @staticmethod
    def ip_of(analysis) -> ipaddress._BaseAddress:
        return ipaddress.ip_address(str(analysis.ip))

    @staticmethod
    def channel_of(analysis) -> str:
        return analysis.channel

    @staticmethod
    def location_of(analysis) -> Optional[tuple]:
        if analysis.latitude is None:
            return None
        return rounded_location(analysis.latitude, analysis.longitude)
