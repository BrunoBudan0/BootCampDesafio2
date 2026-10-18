from decimal import Decimal


def credibility_blend(own_value, own_count: int, reference_value, reference_weight) -> Decimal:
    own_count = Decimal(own_count)
    reference_weight = Decimal(reference_weight)

    if own_count == 0:
        return Decimal(reference_value)

    return (own_count * Decimal(own_value) + reference_weight * Decimal(reference_value)) / (own_count + reference_weight)


def points_weighted_by_history(full_points: int, history_count: int, reference_weight) -> int:
    history_count = Decimal(history_count)
    return int(Decimal(full_points) * history_count // (history_count + Decimal(reference_weight)))
