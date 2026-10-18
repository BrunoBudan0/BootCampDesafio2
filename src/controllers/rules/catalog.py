from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from controllers.rules.credibility import points_weighted_by_history
from controllers.rules.transaction_context import TransactionContext, is_same_owner
from utils.money import brazilian_decimal, brazilian_reais


UNREGISTERED_DEVICE_PIX_LIMIT_CENTS = 20000
UNREGISTERED_DEVICE_DAILY_LIMIT_CENTS = 100000


@dataclass(frozen=True)
class RuleHit:
    code: str
    points: int
    reason: str


class PixRule:
    code = ""

    def evaluate(self, context: TransactionContext) -> Optional[RuleHit]:
        raise NotImplementedError

    def rule_hit(self, points: int, reason: str) -> RuleHit:
        return RuleHit(self.code, points, reason)


def threshold_for_person_type(rule_setting, person_type: str):
    if person_type == "company":
        return rule_setting.company_threshold

    return rule_setting.threshold


class EditablePixRule(PixRule):
    def evaluate(self, context: TransactionContext) -> Optional[RuleHit]:
        rule_setting = context.rule_setting(self.code)

        if not rule_setting.enabled:
            return None

        return self.evaluate_with(context, rule_setting)

    def evaluate_with(self, context: TransactionContext, rule_setting) -> Optional[RuleHit]:
        raise NotImplementedError


class DeviceUsedByManySources(EditablePixRule):
    code = "device_used_by_many_sources"

    def evaluate_with(self, context, rule_setting):
        other_individual_sources = context.pix_analysis_repository.count_other_individual_sources_on_device(
            context.pix.source_device_id, context.pix.source_document_number, context.window_start(rule_setting.window_minutes), context.transaction_date
        )
        individual_sources_on_device = other_individual_sources + (1 if context.pix.source_person_type == "individual" else 0)

        if individual_sources_on_device >= rule_setting.threshold:
            return self.rule_hit(0, f"Aparelho usado por {individual_sources_on_device} pagadores PF diferentes em pouco tempo")
        return None


class ImpossibleTravelOnUnregisteredDevice(EditablePixRule):
    code = "impossible_travel_on_unregistered_device"

    def evaluate_with(self, context, rule_setting):
        travel_speed_kmh = context.travel_speed_kmh

        if travel_speed_kmh is not None and travel_speed_kmh > rule_setting.threshold and not context.is_device_registered:
            return self.rule_hit(0, f"Deslocamento de {travel_speed_text(travel_speed_kmh)} desde o Pix anterior, num aparelho não cadastrado")
        return None


class NewAccountToNewDestinationFarAboveCap(EditablePixRule):
    code = "new_account_to_new_destination_far_above_cap"

    def evaluate_with(self, context, rule_setting):
        far_above_cap_limit_cents = rule_setting.threshold * context.new_account_cap_cents

        if context.is_new_account and context.is_new_destination and context.accumulated_amount_to_destination > far_above_cap_limit_cents:
            return self.rule_hit(
                0,
                f"Conta nova pagando {brazilian_reais(context.accumulated_amount_to_destination)} a um destino novo, "
                f"acima de {brazilian_reais(far_above_cap_limit_cents)}",
            )
        return None


class NightlyLimitExceeded(PixRule):
    code = "nightly_limit_exceeded"

    def evaluate(self, context):
        pix = context.pix
        is_individual_to_individual = pix.source_person_type == "individual" and pix.destination_person_type == "individual"

        if not is_individual_to_individual or not context.is_night:
            return None

        night_total_cents = pix.amount_cents + context.limit_usage_cents_since(
            context.night_start, inclusive=True, destination_person_type="individual"
        )

        if night_total_cents > context.nightly_limit_cents:
            return self.rule_hit(
                0,
                f"Soma da noite de {brazilian_reais(night_total_cents)} acima do limite noturno de {brazilian_reais(context.nightly_limit_cents)}",
            )
        return None


class UnregisteredDeviceLimitExceeded(PixRule):
    code = "unregistered_device_limit_exceeded"

    def evaluate(self, context):
        if context.is_device_registered:
            return None

        if context.pix.amount_cents > UNREGISTERED_DEVICE_PIX_LIMIT_CENTS:
            return self.rule_hit(0, f"Pix de {brazilian_reais(context.pix.amount_cents)} num aparelho não cadastrado, acima de R$ 200,00")

        day_total_on_unregistered_device_cents = context.pix.amount_cents + context.limit_usage_cents_since(
            context.local_day_start, inclusive=True, source_device_id=context.pix.source_device_id
        )

        if day_total_on_unregistered_device_cents > UNREGISTERED_DEVICE_DAILY_LIMIT_CENTS:
            return self.rule_hit(0, f"Soma do dia de {brazilian_reais(day_total_on_unregistered_device_cents)} num aparelho não cadastrado, acima de R$ 1.000,00")
        return None


class ImpossibleTravel(EditablePixRule):
    code = "impossible_travel"

    def evaluate_with(self, context, rule_setting):
        travel_speed_kmh = context.travel_speed_kmh

        if travel_speed_kmh is not None and travel_speed_kmh > rule_setting.threshold and context.is_device_registered:
            return self.rule_hit(rule_setting.points, f"Deslocamento de {travel_speed_text(travel_speed_kmh)} desde o Pix anterior")
        return None


class UnfamiliarValueRule(EditablePixRule):
    value_label = ""

    def value_of(self, context, analysis):
        raise NotImplementedError

    def evaluate_with(self, context, rule_setting):
        if context.is_cold_start or self.value_of(context, context.pix) is None:
            return None

        if not context.is_value_never_seen_in_accepted_history(lambda analysis: self.value_of(context, analysis)):
            return None

        weighted_points = points_weighted_by_history(rule_setting.points, context.accepted_history_count, rule_setting.threshold)

        if weighted_points > 0:
            return self.rule_hit(weighted_points, f"{self.value_label} nunca usado nos {context.accepted_history_count} Pix aceitos do pagador")
        return None


class IpUnfamiliar(UnfamiliarValueRule):
    code = "ip_unfamiliar"
    value_label = "IP"

    def value_of(self, context, analysis):
        return context.ip_of(analysis)


class LocationUnfamiliar(UnfamiliarValueRule):
    code = "location_unfamiliar"
    value_label = "Local"

    def value_of(self, context, analysis):
        return context.location_of(analysis)


class ChannelUnfamiliar(UnfamiliarValueRule):
    code = "channel_unfamiliar"
    value_label = "Canal"

    def value_of(self, context, analysis):
        return context.channel_of(analysis)


class TwoFactorDeniedRecently(EditablePixRule):
    code = "two_factor_denied_recently"

    def evaluate_with(self, context, rule_setting):
        window_start = context.window_start(rule_setting.window_minutes)
        denied_recently = any(
            analysis.two_factor_confirmation is not None
            and analysis.two_factor_confirmation.result == "denied"
            and window_start < analysis.two_factor_confirmation.answered_at <= context.transaction_date
            for analysis in context.source_analyses
        )

        if denied_recently:
            return self.rule_hit(rule_setting.points, "O pagador recusou um 2FA há pouco tempo")
        return None


class NewAccountAboveCap(EditablePixRule):
    code = "new_account_above_cap"

    def evaluate_with(self, context, rule_setting):
        if context.is_new_account and context.accumulated_total_amount > context.new_account_cap_cents:
            return self.rule_hit(
                rule_setting.points,
                f"Conta nova pagando {brazilian_reais(context.accumulated_total_amount)}, "
                f"acima do teto de {brazilian_reais(context.new_account_cap_cents)}",
            )
        return None


class BurstOfPix(EditablePixRule):
    code = "burst_of_pix"

    def evaluate_with(self, context, rule_setting):
        window_start = context.window_start(rule_setting.window_minutes)
        attempts_in_window = 1 + sum(1 for analysis in context.source_analyses if analysis.transaction_date > window_start)

        if attempts_in_window >= threshold_for_person_type(rule_setting, context.pix.source_person_type):
            return self.rule_hit(rule_setting.points, f"{attempts_in_window} Pix do pagador em {rule_setting.window_minutes} minutos")
        return None


def amount_compared_with_the_baseline(context) -> Optional[int]:
    compared_amount = context.accumulated_amount_to_destination

    if context.is_cold_start or compared_amount < context.policy_version.amount_rules_floor_cents:
        return None

    return compared_amount


def exceeds_baseline_multiplier(compared_amount: int, rule_setting, context) -> bool:
    return rule_setting.enabled and compared_amount > rule_setting.threshold * context.baseline_amount


def baseline_reason(compared_amount: int, rule_setting, context) -> str:
    return (
        f"{brazilian_reais(compared_amount)} para o recebedor, acima de {brazilian_decimal(rule_setting.threshold)} vezes a base de "
        f"{brazilian_reais(context.baseline_amount)}"
    )


class AmountFarAboveBaseline(EditablePixRule):
    code = "amount_far_above_baseline"

    def evaluate_with(self, context, rule_setting):
        compared_amount = amount_compared_with_the_baseline(context)

        if compared_amount is not None and exceeds_baseline_multiplier(compared_amount, rule_setting, context):
            return self.rule_hit(rule_setting.points, baseline_reason(compared_amount, rule_setting, context))
        return None


class AmountAboveBaseline(EditablePixRule):
    code = "amount_above_baseline"

    def evaluate_with(self, context, rule_setting):
        compared_amount = amount_compared_with_the_baseline(context)

        if compared_amount is None or not exceeds_baseline_multiplier(compared_amount, rule_setting, context):
            return None

        if exceeds_baseline_multiplier(compared_amount, context.rule_setting(AmountFarAboveBaseline.code), context):
            return None

        return self.rule_hit(rule_setting.points, baseline_reason(compared_amount, rule_setting, context))


class MonthlyVolumeAboveTypical(EditablePixRule):
    code = "monthly_volume_above_typical"

    def evaluate_with(self, context, rule_setting):
        if context.is_cold_start:
            return None

        current_period_length = timedelta(minutes=float(rule_setting.window_minutes))
        current_period_start = context.transaction_date - current_period_length
        reference_start = min(analysis.transaction_date for analysis in context.accepted_history)
        reference_period_length = current_period_start - reference_start

        if reference_period_length < current_period_length:
            return None

        reference_total = sum(
            analysis.amount_cents
            for analysis in context.accepted_history
            if reference_start <= analysis.transaction_date <= current_period_start
        )
        typical_period_volume = reference_total * (current_period_length / reference_period_length)
        current_period_volume = context.pix.amount_cents + context.limit_usage_cents_since(current_period_start)

        if current_period_volume < context.policy_version.amount_rules_floor_cents:
            return None

        if current_period_volume > float(rule_setting.threshold) * typical_period_volume:
            return self.rule_hit(
                rule_setting.points,
                f"Volume de {brazilian_reais(current_period_volume)} em {current_period_length.days} dias, acima de {brazilian_decimal(rule_setting.threshold)} "
                f"vezes o típico de {brazilian_reais(typical_period_volume)}",
            )
        return None


class DestinationAccountOpenedVeryRecently(EditablePixRule):
    code = "destination_account_opened_very_recently"

    def evaluate_with(self, context, rule_setting):
        if context.destination_account_age < timedelta(days=float(rule_setting.threshold)):
            return self.rule_hit(rule_setting.points, f"Conta de destino aberta há {context.destination_account_age.days} dias")
        return None


class DestinationAccountOpenedRecently(EditablePixRule):
    code = "destination_account_opened_recently"

    def evaluate_with(self, context, rule_setting):
        very_recent_rule_setting = context.rule_setting(DestinationAccountOpenedVeryRecently.code)
        is_very_recent = very_recent_rule_setting.enabled and context.destination_account_age < timedelta(days=float(very_recent_rule_setting.threshold))

        if not is_very_recent and context.destination_account_age < timedelta(days=float(rule_setting.threshold)):
            return self.rule_hit(rule_setting.points, f"Conta de destino aberta há {context.destination_account_age.days} dias")
        return None


class NewDestinationAboveUsualCeiling(EditablePixRule):
    code = "new_destination_above_usual_ceiling"

    def evaluate_with(self, context, rule_setting):
        compared_amount = context.accumulated_amount_to_destination
        reaches_the_floor = compared_amount >= context.policy_version.amount_rules_floor_cents
        ceiling_multiplier = threshold_for_person_type(rule_setting, context.pix.destination_person_type)

        if context.is_new_destination and reaches_the_floor and compared_amount > ceiling_multiplier * context.usual_ceiling_amount:
            return self.rule_hit(rule_setting.points, new_destination_reason(compared_amount, ceiling_multiplier, context.usual_ceiling_amount))
        return None


def new_destination_reason(compared_amount: int, ceiling_multiplier, usual_ceiling_amount) -> str:
    if ceiling_multiplier == 1:
        above_the_ceiling = "acima do teto habitual"
    else:
        above_the_ceiling = f"acima de {brazilian_decimal(ceiling_multiplier)} vezes o teto habitual"

    return f"Destino novo recebendo {brazilian_reais(compared_amount)}, {above_the_ceiling} de {brazilian_reais(usual_ceiling_amount)}"


class DestinationReceivingFromManySources(EditablePixRule):
    code = "destination_receiving_from_many_sources"

    def evaluate_with(self, context, rule_setting):
        if context.pix.destination_person_type != "individual":
            return None

        amount_rules_floor_cents = context.policy_version.amount_rules_floor_cents
        other_sources = context.pix_analysis_repository.count_other_sources_paying_destination_at_least(
            context.pix.destination_document_number,
            context.pix.source_document_number,
            amount_rules_floor_cents,
            context.window_start(rule_setting.window_minutes),
            context.transaction_date,
        )
        sources_paying_at_least_the_floor = other_sources + (1 if context.pix.amount_cents >= amount_rules_floor_cents else 0)

        if sources_paying_at_least_the_floor >= rule_setting.threshold:
            return self.rule_hit(rule_setting.points, f"Recebedor PF com {sources_paying_at_least_the_floor} pagadores diferentes em {rule_setting.window_minutes} minutos")
        return None


class DestinationRejectedForOtherSources(EditablePixRule):
    code = "destination_rejected_for_other_sources"

    def __init__(self, own_rule_id: int) -> None:
        self.own_rule_id = own_rule_id

    def evaluate_with(self, context, rule_setting):
        other_sources = context.pix_analysis_repository.count_other_sources_with_destination_rejections(
            context.pix.destination_document_number,
            context.pix.source_document_number,
            self.own_rule_id,
            context.window_start(rule_setting.window_minutes),
            context.transaction_date,
        )

        if other_sources >= rule_setting.threshold:
            return self.rule_hit(rule_setting.points, f"Recebedor com reprovações ou 2FA recusados de {other_sources} outros pagadores")
        return None


class DestinationDocumentInManyAccounts(EditablePixRule):
    code = "destination_document_in_many_accounts"

    def evaluate_with(self, context, rule_setting):
        pix = context.pix
        destination_accounts_of_the_document = context.pix_analysis_repository.find_destination_accounts_between(
            pix.destination_document_number, context.window_start(rule_setting.window_minutes), context.transaction_date
        )
        destination_accounts_of_the_document.add((pix.destination_participant_ispb, pix.destination_branch, pix.destination_account_number))

        if len(destination_accounts_of_the_document) >= threshold_for_person_type(rule_setting, pix.destination_person_type):
            return self.rule_hit(rule_setting.points, f"Recebedor recebendo em {len(destination_accounts_of_the_document)} contas diferentes em pouco tempo")
        return None


class SameOwner(EditablePixRule):
    code = "same_owner"

    def evaluate_with(self, context, rule_setting):
        if is_same_owner(context.pix):
            return self.rule_hit(rule_setting.points, "Pix para conta do mesmo titular")
        return None


class KnownDestination(EditablePixRule):
    code = "known_destination"

    def evaluate_with(self, context, rule_setting):
        if context.accepted_count_to_destination >= rule_setting.threshold:
            return self.rule_hit(rule_setting.points, f"Recebedor com {context.accepted_count_to_destination} Pix aceitos do pagador")
        return None


class LongRegisteredDevice(EditablePixRule):
    code = "long_registered_device"

    def evaluate_with(self, context, rule_setting):
        registered_device = context.registered_device
        old_enough_registration_date = context.transaction_date - timedelta(days=float(rule_setting.threshold))

        if context.is_device_registered and registered_device.registered_at <= old_enough_registration_date:
            return self.rule_hit(rule_setting.points, f"Aparelho cadastrado há {(context.transaction_date - registered_device.registered_at).days} dias")
        return None


def travel_speed_text(travel_speed_kmh: float) -> str:
    if travel_speed_kmh == float("inf"):
        return "distância sem tempo entre os Pix"
    return f"{round(travel_speed_kmh)} km/h"
