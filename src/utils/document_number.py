CPF_LENGTH = 11

CHECK_DIGIT_POSITIONS = [9, 10]


def is_valid_cpf(document_number: str) -> bool:
    """Diz se um CPF existe de verdade — não se ele tem a cara certa.

    O schema em src/schemas/post_sample_entity.json já cobrou o formato:
    três pontos, um hífen, onze dígitos. Isto aqui é outra pergunta, e a
    diferença entre as duas é a lição deste arquivo.

    Os dois últimos dígitos de um CPF não são escolhidos: eles são o
    RESULTADO de uma conta feita sobre os nove primeiros. Por isso um
    número pode ter o formato perfeito e não existir — "111.222.333-44"
    passa no schema e não passa aqui.

    É o mesmo motivo pelo qual a resposta dessa recusa é 422 e não 400:
    não é que a API não conseguiu ler o pedido; ela leu, entendeu, e o
    valor não pode existir.

    A conta, para cada um dos dois dígitos: multiplica cada dígito
    anterior por um peso que decresce, soma tudo, tira o resto da divisão
    por 11. Resto menor que 2 vira dígito 0; nos outros casos, o dígito é
    11 menos o resto.
    """
    digits = []
    for character in document_number:
        if character.isdigit():
            digits.append(int(character))

    if len(digits) != CPF_LENGTH:
        return False

    # Um CPF de dígitos todos iguais ("111.111.111-11") passa na conta
    # dos dígitos verificadores e mesmo assim não vale. São onze números
    # conhecidos, e a Receita não emite nenhum deles.
    all_digits_are_equal = True
    for digit in digits:
        if digit != digits[0]:
            all_digits_are_equal = False
            break

    if all_digits_are_equal:
        return False

    for position in CHECK_DIGIT_POSITIONS:
        total = 0
        first_weight = position + 1

        for index in range(position):
            total = total + digits[index] * (first_weight - index)

        remainder = total % 11

        if remainder < 2:
            expected_digit = 0
        else:
            expected_digit = 11 - remainder

        if digits[position] != expected_digit:
            return False

    return True


CNPJ_LENGTH = 14
CNPJ_FIRST_CHECK_DIGIT_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
CNPJ_SECOND_CHECK_DIGIT_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
DOCUMENT_PUNCTUATION = ".-/"


def normalized_document_number(document_number: str) -> str:
    return "".join(character for character in document_number if character not in DOCUMENT_PUNCTUATION).upper()


def cnpj_check_digit(characters: str, weights: list) -> int:
    remainder = sum((ord(character) - ord("0")) * weight for character, weight in zip(characters, weights)) % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(document_number: str) -> bool:
    cnpj = normalized_document_number(document_number)

    if len(cnpj) != CNPJ_LENGTH or not cnpj[:12].isalnum() or not cnpj[12:].isdigit() or len(set(cnpj)) == 1:
        return False

    first_check_digit = cnpj_check_digit(cnpj[:12], CNPJ_FIRST_CHECK_DIGIT_WEIGHTS)
    second_check_digit = cnpj_check_digit(cnpj[:12] + str(first_check_digit), CNPJ_SECOND_CHECK_DIGIT_WEIGHTS)
    return cnpj[12:] == f"{first_check_digit}{second_check_digit}"


def is_cpf_shaped(document_number: str) -> bool:
    normalized = normalized_document_number(document_number)
    return len(normalized) == CPF_LENGTH and normalized.isdigit()


def is_valid_document_number(document_number: str) -> bool:
    if is_cpf_shaped(document_number):
        return is_valid_cpf(document_number)

    return is_valid_cnpj(document_number)


def person_type_of(document_number: str) -> str:
    return "individual" if is_cpf_shaped(document_number) else "company"
