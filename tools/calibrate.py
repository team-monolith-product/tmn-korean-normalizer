"""사람이 쓴 한국어 산문과 모델 출력에서 지표 값을 재어 경계를 검증한다.

규칙 2·11·12·13은 이 도구로 재어 보고 뺐다. 사람 글에서도 100% 발화해
한국어를 잡을 뿐 AI를 잡지 못했다. 새 지표 규칙을 넣기 전에 먼저 돌려라.

    python3 tools/collect_corpus.py      # 위키백과 2019년 판본 수집
    python3 tools/calibrate.py 지표이름 < 대상.json
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from korean_normalizer.metrics import compute, context_of
from korean_normalizer.segment import Document


def describe(name: str, texts: list[str]) -> dict:
    values = []
    for text in texts:
        value = compute(name, context_of(Document.of(text).prose))
        if value is not None:
            values.append(value)
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(values),
        "min": ordered[0],
        "p25": ordered[len(ordered) // 4],
        "median": statistics.median(ordered),
        "p75": ordered[len(ordered) * 3 // 4],
        "max": ordered[-1],
    }


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("사용: calibrate.py <지표이름> [말뭉치.json ...]")
    name = sys.argv[1]
    for path in sys.argv[2:]:
        docs = json.loads(Path(path).read_text(encoding="utf-8"))
        texts = [d["text"] if isinstance(d, dict) else d for d in docs]
        stats = describe(name, texts)
        summary = "  ".join(
            f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}"
            for k, v in stats.items()
        )
        print(f"{Path(path).stem:24}{summary}")


if __name__ == "__main__":
    main()
