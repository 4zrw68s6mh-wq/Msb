"""Проверка формата и контрольных сумм ИНН."""

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _check(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def normalize_inn(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def validate_inn(inn: str) -> tuple[bool, str]:
    """Возвращает (валиден ли ИНН, сообщение об ошибке)."""
    if not inn.isdigit():
        return False, "ИНН должен состоять только из цифр."
    d = [int(c) for c in inn]
    if len(inn) == 10:
        if _check(d, _W10) != d[9]:
            return False, "Неверная контрольная сумма ИНН юрлица."
        return True, ""
    if len(inn) == 12:
        if _check(d, _W11) != d[10] or _check(d, _W12) != d[11]:
            return False, "Неверная контрольная сумма ИНН ИП/физлица."
        return True, ""
    return False, "ИНН должен содержать 10 цифр (юрлицо) или 12 цифр (ИП)."
