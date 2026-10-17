import random
import string
from uuid import uuid4


CNPJ_FIRST_DIGIT_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
CNPJ_SECOND_DIGIT_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def cnpj_check_digit(characters: str, weights: list) -> int:
    remainder = sum((ord(character) - ord("0")) * weight for character, weight in zip(characters, weights)) % 11
    return 0 if remainder < 2 else 11 - remainder


def format_cnpj(cnpj_number: str) -> str:
    return f"{cnpj_number[0:2]}.{cnpj_number[2:5]}.{cnpj_number[5:8]}/{cnpj_number[8:12]}-{cnpj_number[12:14]}"


class RandomGenerator:
    @staticmethod
    def generate_cpf():
        cpf = [random.randrange(10) for _ in range(9)]
        for _ in range(2):
            value = sum([(len(cpf) + 1 - i) * v for i, v in enumerate(cpf)]) % 11
            cpf.append(11 - value if value > 1 else 0)
        cpf_number = "".join(str(x) for x in cpf)
        cpf_number = f"{cpf_number[0:3]}.{cpf_number[3:6]}.{cpf_number[6:9]}-{cpf_number[9:11]}"
        return cpf_number

    @staticmethod
    def generate_cnpj():
        cnpj = [random.randrange(10) for _ in range(8)] + [0, 0, 0, 1]

        for _ in range(2):
            value = sum(v * (i % 8 + 2) for i, v in enumerate(reversed(cnpj)))
            digit = 11 - value % 11
            cnpj.append(digit if digit < 10 else 0)

        cnpj_number = "".join(str(x) for x in cnpj)

        cnpj_number = (
            f"{cnpj_number[0:2]}.{cnpj_number[2:5]}.{cnpj_number[5:8]}/{cnpj_number[8:12]}-{cnpj_number[12:14]}"
        )

        return cnpj_number

    @staticmethod
    def generate_alphanumeric_cnpj():
        root = "".join(random.choice(string.digits + string.ascii_uppercase) for _ in range(8)) + "0001"
        first_digit = cnpj_check_digit(root, CNPJ_FIRST_DIGIT_WEIGHTS)
        second_digit = cnpj_check_digit(root + str(first_digit), CNPJ_SECOND_DIGIT_WEIGHTS)
        return format_cnpj(f"{root}{first_digit}{second_digit}")

    @staticmethod
    def with_wrong_check_digit(document_number: str) -> str:
        last_digit = int(document_number[-1])
        return document_number[:-1] + str((last_digit + 1) % 10)

    @staticmethod
    def generate_pix_id():
        return f"pix-{uuid4().hex}"

    @staticmethod
    def generate_device_id():
        return f"dvc-{uuid4().hex[:16]}"

    @staticmethod
    def generate_account_number():
        return str(random.randrange(10**5, 10**10))

    @staticmethod
    def generate_branch():
        return f"{random.randrange(1, 10**4):04d}"

    @staticmethod
    def generate_ip():
        return f"10.{random.randrange(256)}.{random.randrange(256)}.{random.randrange(1, 255)}"
