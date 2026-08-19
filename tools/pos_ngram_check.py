"""품사 n-gram 다양성이 사람 글과 LLM 글을 가르는지 잰다.

규칙 13의 근거를 확인하려고 만들었다. 결론은 가르지 못한다는 것이다.
원문 그대로 재면 AUC가 0.88까지 나오지만 길이를 맞추면 0.5로 떨어진다.
다양성 비율은 글이 길수록 낮아지는데 LLM 글이 사람 글보다 길어서 생긴
착시다. KatFish 에세이 기준 사람 364토큰, LLM 490토큰이다.

말뭉치는 논문 저자 저장소에 있다.
Shinwoo-Park/detecting_llm_generated_korean_text_through_linguistic_analysis

    python3 tools/pos_ngram_check.py katfish/katfish_dataset/essay.jsonl
"""

import collections
import json
import math
import statistics
import sys
from pathlib import Path

from kiwipiepy import Kiwi

WINDOW = 150
kiwi = Kiwi()


def tags_of(text: str) -> list[str]:
    return [token.tag for token in kiwi.tokenize(text)]


def grams(tags: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tags[i : i + n]) for i in range(len(tags) - n + 1)]


def diversity(tags: list[str], n: int) -> float:
    got = grams(tags, n)
    return len(set(got)) / len(got)


def entropy(tags: list[str], n: int) -> float:
    counts = collections.Counter(grams(tags, n))
    total = sum(counts.values())
    return -sum((v / total) * math.log2(v / total) for v in counts.values())


def auc(positive: list[float], negative: list[float]) -> float:
    merged = sorted([(v, 1) for v in positive] + [(v, 0) for v in negative])
    rank_sum, index = 0.0, 0
    while index < len(merged):
        stop = index
        while stop < len(merged) and merged[stop][0] == merged[index][0]:
            stop += 1
        mid = (index + stop + 1) / 2
        rank_sum += sum(mid for _, label in merged[index:stop] if label == 1)
        index = stop
    return (rank_sum - len(positive) * (len(positive) + 1) / 2) / (
        len(positive) * len(negative)
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("사용: pos_ngram_check.py <katfish jsonl>")
    with Path(sys.argv[1]).open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    human = [tags_of(r["text"]) for r in rows if r["written_by"] == "human"]
    llm = [tags_of(r["text"]) for r in rows if r["written_by"] != "human"]
    print(f"사람 {len(human)}건 · LLM {len(llm)}건")
    print(
        f"토큰 중앙 사람 {statistics.median(map(len, human)):.0f} "
        f"· LLM {statistics.median(map(len, llm)):.0f}\n"
    )

    for label, cut in (("원문 그대로", None), (f"앞 {WINDOW}토큰만", WINDOW)):
        if cut:
            h = [t[:cut] for t in human if len(t) >= cut]
            m = [t[:cut] for t in llm if len(t) >= cut]
        else:
            h, m = human, llm
        print(f"[{label}] 사람 {len(h)} LLM {len(m)}")
        for name, fn in (("다양성", diversity), ("엔트로피", entropy)):
            cells = [
                f"{n}-gram {auc([fn(t, n) for t in h], [fn(t, n) for t in m]):.3f}"
                for n in (2, 3, 4)
            ]
            print(f"  {name:8}" + "  ".join(cells))
        print()


if __name__ == "__main__":
    main()
