"""통계 지표와 비문 검사에서 같은 형태소 분석기를 공유한다."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kiwipiepy import Kiwi


@lru_cache(maxsize=1)
def get_analyzer() -> Kiwi | None:
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        return None
    return Kiwi(num_workers=1)
