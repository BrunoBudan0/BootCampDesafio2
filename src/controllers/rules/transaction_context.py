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
LOCATION_ROUNDING_PLACES = Decimal("0.01")
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
    return pix.source_document_number == pix.destination_document_number


def is_pending_two_factor_at(analysis: PixAnalysis, moment: datetime) -> bool:
    return (
        analysis.decision.enumerator == "two_factor_required"
        and analysis.two_factor_confirmation is None
        and analysis.two_factor_expires_at > moment
    )


def rounded_location(latitude, longitude) -> tuple:
    return (
        Decimal(latitude).quantize(LOCATION_ROUNDING_PLACES, rounding=ROUND_HALF_UP),
        Decimal(longitude).quantize(LOCATION_ROUNDING_PLACES, rounding=ROUND_HALF_UP),
    )


def haversine_distance_km(first_latitude, first_longitude, second_latitude, second_longitude) -> float:
    first_latitude_radians, first_longitude_radians, second_latitude_radians, second_longitude_radians = map(radians, map(float, (first_latitude, first_longitude, second_latitude, second_longitude)))
    haversine_of_central_angle = (
        sin((second_latitude_radians - first_latitude_radians) / 2) ** 2
        + cos(first_latitude_radians) * cos(second_latitude_radians) * sin((second_longitude_radians - first_longitude_radians) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine_of_central_angle))


def nightly_limit_in_force(nightly_limits: list, moment: datetime) -> int:
    limits_requested_until_moment = [nightly_limit for nightly_limit in nightly_limits if nightly_limit.requested_at <= moment]

    while limits_requested_until_moment:
        latest_requested_limit = max(limits_requested_until_moment, key=lambda nightly_limit: (nightly_limit.requested_at, nightly_limit.id or 0))
        if latest_requested_limit.effective_at <= moment:
            return latest_requested_limit.nightly_limit_cents
        limits_requested_until_moment = [nightly_limit for nightly_limit in limits_requested_until_moment if nightly_limit.requested_at < latest_requested_limit.requested_at]

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
        self.policy_version = policy_version
        self.rule_settings_by_code = {setting.rule.code: setting for setting in policy_version.rule_settings}
        self.pix_analysis_repository = pix_analysis_repository
        self.source_repository = source_repository
        self.transaction_date = pix.transaction_date

    def rule_setting(self, rule_code: str):
        return self.rule_settings_by_code[rule_code]

    def window_start(self, minutes) -> datetime:
        return self.transaction_date - timedelta(minutes=float(minutes))

    @cached_property
    def source_analyses_lookback_minutes(self) -> float:
        window_lengths_in_minutes = [
            self.policy_version.history_window_days * 1440,
            self.policy_version.short_term_window_minutes,
            1440,
        ]
        window_lengths_in_minutes.extend(
            setting.window_minutes
            for setting in self.policy_version.rule_settings
            if setting.window_minutes is not None
        )
        return float(max(window_lengths_in_minutes))

    @cached_property
    def source_analyses(self) -> list:
        return self.pix_analysis_repository.find_source_analyses_between(
            self.pix.source_document_number, self.window_start(self.source_analyses_lookback_minutes), self.transaction_date
        )

    @cached_property
    def history_start(self) -> datetime:
        return self.transaction_date - timedelta(days=self.policy_version.history_window_days)

    @cached_property
    def accepted_history(self) -> list:
        return [
            analysis
            for analysis in self.source_analyses
            if analysis.transaction_date > self.history_start and is_accepted(analysis)
        ]

    @property
    def accepted_history_count(self) -> int:
        return len(self.accepted_history)

    @property
    def is_cold_start(self) -> bool:
        return self.accepted_history_count == 0

    @cached_property
    def limit_consuming_analyses(self) -> list:
        return [
            analysis
            for analysis in self.source_analyses
            if is_accepted(analysis) or is_pending_two_factor_at(analysis, self.transaction_date)
        ]

    def limit_usage_cents_since(self, since: datetime, inclusive: bool = False, **matching_fields) -> int:
        used_cents = 0
        for analysis in self.limit_consuming_analyses:
            is_in_window = analysis.transaction_date >= since if inclusive else analysis.transaction_date > since
            if is_in_window and all(getattr(analysis, field) == value for field, value in matching_fields.items()):
                used_cents += analysis.amount_cents
        return used_cents

    @cached_property
    def accumulated_total_amount(self) -> int:
        return self.pix.amount_cents + self.limit_usage_cents_since(self.window_start(self.policy_version.short_term_window_minutes))

    @cached_property
    def accumulated_amount_to_destination(self) -> int:
        return self.pix.amount_cents + self.limit_usage_cents_since(
            self.window_start(self.policy_version.short_term_window_minutes),
            destination_document_number=self.pix.destination_document_number,
        )

    @cached_property
    def accepted_amounts_of_the_same_person_type_pair(self) -> list:
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
        return getattr(self.policy_version, f"reference_average_ticket_{pair_name}_cents")

    @cached_property
    def population_median_amount(self) -> Decimal:
        population_accepted_count, population_observed_median_cents = self.pix_analysis_repository.count_and_median_of_population_accepted_amounts(
            self.pix.source_person_type, self.pix.destination_person_type, self.history_start, self.transaction_date
        )
        if population_accepted_count == 0:
            return Decimal(self.reference_average_ticket_cents)

        return credibility_blend(
            Decimal(str(population_observed_median_cents)), population_accepted_count, self.reference_average_ticket_cents, self.policy_version.population_median_reference_weight
        )

    @cached_property
    def baseline_amount(self) -> Decimal:
        if not self.accepted_amounts_of_the_same_person_type_pair:
            return self.population_median_amount

        return credibility_blend(
            Decimal(str(statistics.median(self.accepted_amounts_of_the_same_person_type_pair))),
            len(self.accepted_amounts_of_the_same_person_type_pair),
            self.population_median_amount,
            self.policy_version.source_baseline_reference_weight,
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
        short_term_start = self.window_start(self.policy_version.short_term_window_minutes)
        return [analysis for analysis in self.accepted_history if analysis.transaction_date <= short_term_start]

    @cached_property
    def known_destination_documents(self) -> set:
        return {analysis.destination_document_number for analysis in self.accepted_history_before_short_term}

    @property
    def is_new_destination(self) -> bool:
        return self.pix.destination_document_number not in self.known_destination_documents

    @cached_property
    def accepted_count_to_destination(self) -> int:
        return sum(
            1
            for analysis in self.accepted_history_before_short_term
            if analysis.destination_document_number == self.pix.destination_document_number
        )

    @property
    def is_new_account(self) -> bool:
        return self.transaction_date - self.pix.source_account_opening_date < timedelta(days=self.policy_version.new_account_age_days)

    @property
    def new_account_cap_cents(self) -> int:
        if self.pix.source_person_type == "individual":
            return self.policy_version.new_account_cap_individual_cents

        return self.policy_version.new_account_cap_company_cents

    @property
    def destination_account_age(self) -> timedelta:
        return self.transaction_date - self.pix.destination_account_opening_date

    @cached_property
    def registered_device(self):
        return self.source_repository.find_registered_device(self.pix.source_document_number, self.pix.source_device_id)

    @property
    def is_device_registered(self) -> bool:
        return self.registered_device is not None and self.registered_device.registered_at <= self.transaction_date

    @cached_property
    def source_has_any_accepted_pix(self) -> bool:
        return self.pix_analysis_repository.source_has_any_accepted_pix(self.pix.source_document_number)

    @cached_property
    def last_located_accepted_pix(self) -> Optional[PixAnalysis]:
        accepted_pix_with_location = [analysis for analysis in self.accepted_history if analysis.source_latitude is not None]
        return accepted_pix_with_location[-1] if accepted_pix_with_location else None

    @cached_property
    def travel_speed_kmh(self) -> Optional[float]:
        last_located_pix = self.last_located_accepted_pix

        if last_located_pix is None or not self.pix.has_geolocation:
            return None

        distance_from_last_located_pix_km = haversine_distance_km(
            last_located_pix.source_latitude, last_located_pix.source_longitude, self.pix.source_latitude, self.pix.source_longitude
        )

        if distance_from_last_located_pix_km < IMPOSSIBLE_TRAVEL_MINIMUM_DISTANCE_KM:
            return None

        elapsed_hours = (self.transaction_date - last_located_pix.transaction_date).total_seconds() / 3600

        if elapsed_hours <= 0:
            return float("inf") if distance_from_last_located_pix_km > 0 else 0.0

        return distance_from_last_located_pix_km / elapsed_hours

    @cached_property
    def local_time(self) -> datetime:
        return self.transaction_date.astimezone(timezone(timedelta(minutes=self.pix.transaction_utc_offset_minutes)))

    @property
    def is_night(self) -> bool:
        local_clock_time = self.local_time.time()
        return local_clock_time >= NIGHT_STARTS_AT or local_clock_time < NIGHT_ENDS_AT

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
        return nightly_limit_in_force(self.source_repository.find_nightly_limits(self.pix.source_document_number), self.transaction_date)

    def is_value_never_seen_in_accepted_history(self, value_of) -> bool:
        return all(value_of(analysis) != value_of(self.pix) for analysis in self.accepted_history)

    @staticmethod
    def ip_of(analysis) -> ipaddress._BaseAddress:
        return ipaddress.ip_address(str(analysis.source_ip))

    @staticmethod
    def channel_of(analysis) -> str:
        return analysis.source_channel

    @staticmethod
    def location_of(analysis) -> Optional[tuple]:
        if analysis.source_latitude is None:
            return None
        return rounded_location(analysis.source_latitude, analysis.source_longitude)
