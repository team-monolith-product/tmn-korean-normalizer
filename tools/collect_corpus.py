"""사람이 쓴 한국어 산문 말뭉치를 모은다.

LLM 이전임을 보장하려고 2019-12-31 이전 판본만 가져온다. 그 뒤 판본은
AI 도움을 받은 편집이 섞였을 수 있다.
"""

import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

OUT = pathlib.Path(__file__).parent / "human_corpus.json"
CUTOFF = "2019-12-31T00:00:00Z"
UA = {"User-Agent": "korean-normalizer-calibration/0.1 (research; contact via github)"}


def api(host: str, params: dict) -> dict:
    url = f"https://{host}/w/api.php?" + urllib.parse.urlencode(
        {**params, "format": "json"}
    )
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def featured_titles(limit: int) -> list[str]:
    found, offset = [], 0
    while len(found) < limit:
        data = api(
            "ko.wikipedia.org",
            {
                "action": "query",
                "list": "search",
                "srsearch": 'incategory:"알찬 글"',
                "srlimit": 50,
                "sroffset": offset,
            },
        )
        hits = data.get("query", {}).get("search", [])
        if not hits:
            break
        found += [h["title"] for h in hits]
        offset += len(hits)
    return found[:limit]


def revision_before_cutoff(host: str, title: str) -> str | None:
    """지정 시점 이전의 마지막 판본 본문."""
    data = api(
        host,
        {
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvprop": "content|timestamp",
            "rvslots": "main",
            "rvstart": CUTOFF,
            "rvdir": "older",
            "rvlimit": 1,
        },
    )
    for page in data.get("query", {}).get("pages", {}).values():
        for rev in page.get("revisions", []):
            return rev["slots"]["main"].get("*")
    return None


WIKI_NOISE = [
    (re.compile(r"\{\{[^{}]*\}\}", re.S), " "),  # 틀
    (re.compile(r"\{\|.*?\|\}", re.S), " "),  # 표
    (re.compile(r"<ref[^>]*>.*?</ref>", re.S), " "),  # 각주
    (re.compile(r"<ref[^>]*/>"), " "),
    (re.compile(r"<[^>]+>"), " "),  # 태그
    (re.compile(r"\[\[(?:파일|그림|File|Image):[^\]]*\]\]", re.I), " "),
    (re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]"), r"\1"),  # 링크 표시문만
    (re.compile(r"\[\[([^\]]*)\]\]"), r"\1"),
    (re.compile(r"'''?"), ""),  # 굵게/기울임
    (re.compile(r"^\s*[*#:;].*$", re.M), ""),  # 목록
    (re.compile(r"^\s*=+.*=+\s*$", re.M), ""),  # 문단 제목
    (re.compile(r"\[https?://\S+[^\]]*\]"), " "),
    (re.compile(r"\n{3,}"), "\n\n"),
]


def to_prose(wikitext: str) -> str:
    text = wikitext
    for _ in range(3):  # 중첩 틀은 여러 번 지워야 걷힌다
        for pattern, repl in WIKI_NOISE:
            text = pattern.sub(repl, text)
    lines = [ln.strip() for ln in text.split("\n")]
    keep = [ln for ln in lines if len(ln) > 40 and not ln.startswith(("|", "!", "{"))]
    return "\n\n".join(keep)


def main() -> None:
    titles = featured_titles(60)
    print(f"알찬 글 {len(titles)}편 확인, 2019년 판본 수집")
    docs = []
    for title in titles:
        try:
            raw = revision_before_cutoff("ko.wikipedia.org", title)
        except Exception as failure:
            print(f"  {title[:20]:22} 실패 {failure}")
            continue
        if not raw:
            continue
        prose = to_prose(raw)
        if len(prose) < 1500:
            continue
        docs.append({"source": "위키백과 알찬 글", "title": title, "text": prose})
        print(f"  {title[:20]:22} {len(prose):>6}자")
        time.sleep(0.15)
        if len(docs) >= 30:
            break
    OUT.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    total = sum(len(d["text"]) for d in docs)
    print(f"\n저장 {OUT} · {len(docs)}편 · 총 {total:,}자")


if __name__ == "__main__":
    main()
