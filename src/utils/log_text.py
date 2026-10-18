import re


DOCUMENT_IN_PATH = re.compile(r"^/sources/[^/]+")
MASKED_DOCUMENT_PATH = "/sources/***"
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
NULL_CHARACTER = "\x00"


def loggable_text(text: str) -> str:
    return CONTROL_CHARACTERS.sub("?", text).encode("utf-8", "replace").decode("utf-8")


def storable_text(text: str) -> str:
    return text.replace(NULL_CHARACTER, "?").encode("utf-8", "replace").decode("utf-8")


def loggable_path(path: str) -> str:
    return loggable_text(DOCUMENT_IN_PATH.sub(MASKED_DOCUMENT_PATH, path))
