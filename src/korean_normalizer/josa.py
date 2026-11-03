"""조사 형태를 앞 어절의 받침에 맞춘다.

'-들'을 지우면 앞말의 받침이 사라져 조사가 어긋난다. 사용자들이 -> 사용자이
같은 비문을 막으려면 치환 뒤에 조사를 다시 골라야 한다.
"""

from __future__ import annotations

HANGUL_BASE = 0xAC00
HANGUL_LAST = 0xD7A3
JONGSEONG_COUNT = 28

ALLOMORPHS = (
    ("이", "가"),
    ("은", "는"),
    ("을", "를"),
    ("과", "와"),
    ("으로", "로"),
)

_AFTER_BATCHIM = {form: pair[0] for pair in ALLOMORPHS for form in pair}
_AFTER_VOWEL = {form: pair[1] for pair in ALLOMORPHS for form in pair}


def has_batchim(word: str) -> bool | None:
    """마지막 글자에 받침이 있으면 True. 한글이 아니면 None."""
    if not word:
        return None
    last = ord(word[-1])
    if not HANGUL_BASE <= last <= HANGUL_LAST:
        return None
    return (last - HANGUL_BASE) % JONGSEONG_COUNT != 0


def agree(stem: str, josa: str) -> str:
    """stem 뒤에 올 josa의 올바른 형태를 반환한다.

    판정할 수 없으면 원래 형태를 그대로 돌려준다.
    """
    if not josa or josa not in _AFTER_BATCHIM:
        return josa
    batchim = has_batchim(stem)
    if batchim is None:
        return josa
    if josa in {"으로", "로"} and (ord(stem[-1]) - HANGUL_BASE) % JONGSEONG_COUNT == 8:
        return "로"
    return _AFTER_BATCHIM[josa] if batchim else _AFTER_VOWEL[josa]
