from decimal import ROUND_HALF_UP, Decimal


def brazilian_reais(amount_cents) -> str:
    reais = (Decimal(amount_cents) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, cents = f"{reais:.2f}".split(".")
    whole_with_thousands = f"{int(whole):,}".replace(",", ".")
    return f"R$ {whole_with_thousands},{cents}"


def brazilian_decimal(value) -> str:
    return f"{Decimal(value).normalize():f}".replace(".", ",")
