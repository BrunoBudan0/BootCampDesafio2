ERROR_BODY_FIELDS = {"title", "description", "translation", "code"}


def assert_error(status: int, body: dict, expected_status: int, expected_code: str) -> None:
    assert status == expected_status, f"Esperava HTTP {expected_status} e veio {status}: {body}"
    assert body is not None, "A resposta de erro veio sem corpo JSON"
    assert set(body) == ERROR_BODY_FIELDS, f"O corpo do erro não segue o formato {ERROR_BODY_FIELDS}: {body}"
    assert body["code"] == expected_code, f"Esperava o código {expected_code} e veio {body['code']}"


def rule_codes(analysis: dict) -> set:
    return {rule_hit["code"] for rule_hit in analysis["metadata"]["rules"]}


def rule_hit(analysis: dict, code: str) -> dict:
    for hit in analysis["metadata"]["rules"]:
        if hit["code"] == code:
            return hit
    raise AssertionError(f"A regra {code} não disparou. Dispararam: {sorted(rule_codes(analysis))}")


def assert_rule_fired(analysis: dict, code: str) -> None:
    assert code in rule_codes(analysis), f"A regra {code} devia disparar. Dispararam: {sorted(rule_codes(analysis))}"


def assert_rule_not_fired(analysis: dict, code: str) -> None:
    assert code not in rule_codes(analysis), f"A regra {code} não devia disparar. Dispararam: {sorted(rule_codes(analysis))}"
