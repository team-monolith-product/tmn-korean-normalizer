# tmn-korean-normalizer

한국어 AI 작문 패턴 40가지를 규칙으로 검출하고, 그중 판단이 필요 없는 9가지를 자동 교정한다.

[DaleSeo/korean-skills](https://github.com/DaleSeo/korean-skills)의 humanizer 스킬은 40개 패턴을
LLM이 매번 읽고 눈대중으로 판정한다. 그 판정 중 기계가 할 수 있는 부분을 정규식과 통계 지표로
옮긴 것이 이 도구다. LLM은 남은 의미 판단만 맡는다.

## 무엇이 규칙으로 옮겨졌나

| 계층 | 패턴 | 개수 | 처리 |
|---|---|---|---|
| A | 3, 6, 7, 15, 17, 19, 27, 31, 37 | 9 | 검출 + 자동 교정 |
| B | 1, 2, 4, 5, 8~10, 14, 16, 18, 20~26, 28~30, 32~36, 38~40 | 28 | 검출만, 교정은 사람이나 LLM |
| C | 11, 12, 13 | 3 | 형태소 분석기가 있을 때만 검출 |

Tier A는 예외가 없는 규칙이다. 이중 피동 `되어진다`는 한국어 어문 규범상 비문이고,
`~에 있어서`는 원본 문서가 자연스러운 사용처가 없다고 규정한다. 나머지는 빈도 임계를
넘겼다는 사실만 알려주고 어떻게 고칠지는 판단에 맡긴다.

**패턴 8~10 띄어쓰기는 자동 교정하지 않는다.** 원본 스킬이 제시하는 교정 예시
`할 수 있는것`, `공부하고있습니다`는 한글 맞춤법 제42항 의존명사 띄어쓰기와 제47항
보조용언 규정을 어긴다. KatFishNet이 관측한 것은 인간 텍스트의 띄어쓰기 분산이 크다는
통계지 붙여 쓰는 편이 옳다는 규범이 아니다. 검출만 하고 판단은 사람에게 넘긴다.

## 설치

```bash
uv sync
```

품사 지표(패턴 11~13)까지 쓰려면 형태소 분석기를 함께 설치한다.

```bash
uv sync --extra pos
```

## 사용

```bash
uv run korean-normalizer detect 문서.md
```

```
자연도 등급: C — S1 4건, S2 4건으로 AI 흔적이 뚜렷함
감지 요약: S1 4건, S2 4건, S3 0건

[S1] 패턴 31 이중 피동 '~되어진다' — 문서 전체, 3회 (임계 1) [자동교정]
    지침: 단일 피동으로 되돌린다. 행위자가 분명하면 능동으로 바꾼다.
    · 데이터는 신중하게 분석되어집니다. 결과는 통계적으
```

JSON으로 받아 다른 도구에 넘길 수도 있다.

```bash
uv run korean-normalizer detect 문서.md --format json
```

Tier A 자동 교정은 diff로 먼저 확인하고 반영한다.

```bash
uv run korean-normalizer fix 문서.md --diff
uv run korean-normalizer fix 문서.md --in-place
```

CI에서 문서를 검사하려면 종료 코드를 쓴다.

```bash
uv run korean-normalizer detect 문서.md --fail-on-finding
```

규칙 목록은 다음으로 확인한다.

```bash
uv run korean-normalizer rules
```

## 동작 원리

1. 코드 블록, 인라인 코드, URL, 마크다운 링크 타깃을 자리표시자로 덮는다. 오프셋은 그대로
   두어 원문에서 스니펫을 다시 잘라낸다. 큰따옴표 직접 인용은 검출은 하되 교정에서 제외한다.
2. 문단과 문장으로 나눈다.
3. `rules/*.json`의 규칙을 적용한다. 정규식 규칙은 문서 또는 문단 단위로 빈도 임계를 확인하고,
   통계 규칙은 지표를 계산해 경계와 비교한다. 표본이 모자라면 판정을 건너뛰고 그 사실을 남긴다.
4. S1/S2 건수로 자연도 등급 A~D를 매긴다.
5. `fix`는 임계를 실제로 넘긴 자리에서만 치환한다. 1회 등장이 자연스러운 표현을 건드리지 않기
   위해서다. 치환이 다른 규칙의 대상을 만들 수 있어 결과가 안정될 때까지 최대 3회 순회한다.

`-들`을 지우면 앞말의 받침이 사라져 조사가 어긋난다. `사용자들이`에서 `들`만 빼면
`사용자이`가 되므로, 치환 뒤 받침을 보고 조사를 다시 고른다.

## 규칙 추가

`src/korean_normalizer/rules/*.json`에 항목을 더한다. 코드 수정은 필요 없다.

```json
{
  "id": 41,
  "name": "패턴 이름",
  "severity": "S2",
  "kind": "regex",
  "pattern": "정규식",
  "exclude": "예외 정규식",
  "threshold": { "scope": "paragraph", "count": 3 },
  "autofix": [{ "pattern": "찾을 것", "replacement": "바꿀 것" }],
  "guidance": "교정 지침 한 줄"
}
```

통계 규칙은 `"kind": "metric"`으로 두고 `metrics.py`에 등록한 지표 이름과 경계를 적는다.
`autofix`를 넣는 순간 그 규칙은 Tier A가 되므로, 반례가 없는지 먼저 확인한다.

## Claude Code 스킬로 쓰기

```bash
ln -s ~/repo/tmn-korean-normalizer/skill ~/.claude/skills/korean-normalizer
```

스킬은 CLI로 검출과 기계적 교정을 끝낸 뒤 남은 findings만 LLM이 처리하게 한다.

## 개발

```bash
uv run pytest -q --cov=korean_normalizer
uv run ruff check src tests
```

## 근거와 출처

- 패턴 정의, S1/S2/S3 심각도, 자연도 등급: [DaleSeo/korean-skills](https://github.com/DaleSeo/korean-skills) (MIT)
- 통계 근거: [KatFishNet, arXiv:2503.00032](https://arxiv.org/abs/2503.00032)
- 형태소 분석기: [kiwipiepy](https://github.com/bab2min/kiwipiepy)
- 맞춤법 규정: [국립국어원 어문규범](https://kornorms.korean.go.kr/regltn/regltnView.do?regltn_code=0001)
