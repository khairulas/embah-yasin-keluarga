"""
Parse Malay/Indonesian names for GEDCOM export.

Handled conventions:
  - Patronymic: "X bin Y" (male) / "X binti Y" (female), also "bt", "bte"
  - Religious titles: Haji, Hajah, Kiyai, Tuan Haji, Puan Hajah, Syed, Sharifah
  - Deceased markers (NOT titles, stripped entirely): Almarhum, Almarhumah,
    Allahyarham, Allahyarhamah
  - Spouse rank annotations like "(Isteri pertama)" stripped before parsing
"""
import re

DECEASED_MARKERS = {
    "almarhum", "almarhumah", "allahyarham", "allahyarhamah", "arwah",
}

TITLE_PREFIXES = {
    "haji", "hajah", "haj",
    "kiyai", "kiai", "kyai",
    "tuan", "puan",
    "syed", "sharifah", "syarifah",
    "ustaz", "ustazah",
    "dato", "datuk", "datin",
    "tun", "toh",
}

PATRONYMIC_MARKERS = {"bin", "binti", "bt", "bte", "binte"}

_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")


def parse_name(full_name: str) -> dict:
    if not full_name:
        return {"npfx": "", "given": "", "surname": "", "suffix": "",
                "is_deceased_marker": False}

    name = _PAREN_RE.sub(" ", full_name).strip()
    tokens = name.split()

    is_deceased_marker = False
    cleaned = []
    for tok in tokens:
        if tok.lower().rstrip(".,") in DECEASED_MARKERS:
            is_deceased_marker = True
        else:
            cleaned.append(tok)
    tokens = cleaned

    patronymic_idx = None
    for i, tok in enumerate(tokens):
        if tok.lower() in PATRONYMIC_MARKERS:
            patronymic_idx = i
            break

    if patronymic_idx is None:
        npfx_tokens, given_tokens = _split_titles(tokens)
        return {
            "npfx": " ".join(npfx_tokens),
            "given": " ".join(given_tokens),
            "surname": "",
            "suffix": "",
            "is_deceased_marker": is_deceased_marker,
        }

    pre = tokens[:patronymic_idx]
    post = tokens[patronymic_idx + 1:]

    npfx_tokens, given_tokens = _split_titles(pre)
    father_titles, father_name = _split_titles(post)

    return {
        "npfx": " ".join(npfx_tokens),
        "given": " ".join(given_tokens),
        "surname": " ".join(father_name),
        "suffix": " ".join(father_titles),
        "is_deceased_marker": is_deceased_marker,
    }


def _split_titles(tokens):
    titles, rest = [], list(tokens)
    while rest and rest[0].lower().rstrip(".,") in TITLE_PREFIXES:
        titles.append(rest.pop(0))
    return titles, rest


def to_gedcom_name(parsed: dict) -> str:
    given = parsed["given"] or ""
    surname = parsed["surname"] or ""
    return f"{given} /{surname}/".strip()