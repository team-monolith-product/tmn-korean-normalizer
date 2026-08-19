# tmn-korean-normalizer

한국어 AI 작문 패턴을 규칙으로 검출하고, 그중 판단이 필요 없는 9가지를 자동 교정한다.

[DaleSeo/korean-skills](https://github.com/DaleSeo/korean-skills)의 humanizer 스킬은 40개 패턴을
LLM이 매번 읽고 눈대중으로 판정한다. 그 판정 중 기계가 할 수 있는 부분을 정규식과 통계 지표로
옮긴 것이 이 도구다. LLM은 남은 의미 판단만 맡는다.

## 무엇이 규칙으로 옮겨졌나

| 계층 | 패턴 | 개수 | 처리 |
|---|---|---|---|
| A | 3, 6, 7, 15, 17, 19, 27, 31, 37 | 9 | 검출 + 자동 교정 |
| B | 1, 2, 4, 5, 8~10, 14, 16, 18, 20~26, 28~30, 32~36, 38~40 | 28 | 검출만, 교정은 사람이나 LLM |
| C | 11, 12, 13 | 3 | 형태소 분석기가 있을 때만 검출 |

1~40번은 원본 스킬을 그대로 옮긴 것이다. 101번부터는 팀이 실사용에서 찾아 덧붙인 규칙이고
`rules/extra.json`에 따로 둔다. 원본 집합을 건드리지 않으려고 번호대를 나눴다.

| 번호 | 패턴 | 잡는 것 |
|---|---|---|
| 101 | '하나의' 부정관사 직역 | 영어 a/an을 옮긴 `하나의 완벽한 웹 페이지` |
| 102 | 지시대명사 복수형 | `이것들`, `그것들`, 무생물을 가리키는 `이들` |
| 103 | 피동 중복 | `반복되어 사용되는`처럼 피동이 겹친 형태 |
| 104 | 완전무결 과장 | `완벽한`, `최고의`, `유일무이` |

Tier A는 예외가 없는 규칙이다. 이중 피동 `되어진다`는 한국어 어문 규범상 비문이고,
`~에 있어서`는 원본 문서가 자연스러운 사용처가 없다고 규정한다. 나머지는 빈도 임계를
넘겼다는 사실만 알려주고 어떻게 고칠지는 판단에 맡긴다.

**패턴 8~10 띄어쓰기는 자동 교정하지 않는다.** 원본 스킬이 제시하는 교정 예시
`할 수 있는것`, `공부하고있습니다`는 한글 맞춤법 제42항 의존명사 띄어쓰기와 제47항
보조용언 규정을 어긴다. KatFishNet이 관측한 것은 인간 텍스트의 띄어쓰기 분산이 크다는
통계지 붙여 쓰는 편이 옳다는 규범이 아니다. 검출만 하고 판단은 사람에게 넘긴다.

## 설치

레포를 클론한다. 팀 관례상 `~/teammono` 아래에 둔다.

```bash
git clone git@github.com:team-monolith-product/tmn-korean-normalizer.git ~/teammono/tmn-korean-normalizer
```

### 쓰기만 할 때

전역 명령으로 설치한다. 어느 디렉터리에서든 `korean-normalizer`를 쓸 수 있다.

```bash
uv tool install ~/teammono/tmn-korean-normalizer
```

품사 지표까지 쓰려면 형태소 분석기를 함께 넣는다. 없으면 패턴 11~13은 건너뛴다.

```bash
uv tool install --with kiwipiepy ~/teammono/tmn-korean-normalizer
```

갱신은 다음과 같이 한다.

```bash
cd ~/teammono/tmn-korean-normalizer && git pull && uv tool install --force .
```

### 고칠 때

레포 안에서 개발용 가상환경을 만든다. pytest와 ruff가 함께 설치된다.

```bash
cd ~/teammono/tmn-korean-normalizer
uv sync --extra pos
uv run korean-normalizer detect examples/ai-sample.md
```

## 사용

아래는 전역 설치를 기준으로 한다. 개발 환경에서는 앞에 `uv run`을 붙인다.

```bash
korean-normalizer detect examples/ai-sample.md
```

```
자연도 등급: C — S1 4건, S2 4건으로 AI 흔적이 뚜렷함
감지 요약: S1 4건, S2 4건, S3 0건

[S1] 패턴 27 '~에 있어서' 격식 차용 — 문서 전체, 2회 (임계 1) [자동교정]
    지침: ~에서, ~의 경우로 환원하거나 통째로 지운다.
    · 되어집니다. 현대 사회에 있어서 데이터의 중요성은 매
    · 성은 매우 크다. 이 점에 있어서 모든 기업이 동의한다
```

JSON으로 받아 다른 도구에 넘길 수도 있다.

```bash
korean-normalizer detect 문서.md --format json
```

표준 입력도 받는다.

```bash
cat 문서.md | korean-normalizer detect
```

Tier A 자동 교정은 diff로 먼저 확인하고 반영한다.

```bash
korean-normalizer fix 문서.md --diff
korean-normalizer fix 문서.md --in-place
```

CI에서 문서를 검사하려면 종료 코드를 쓴다.

```bash
korean-normalizer detect 문서.md --fail-on-finding
```

규칙 목록과 tier는 다음으로 확인한다.

```bash
korean-normalizer rules
```

## 동작 원리

1. 산문이 아닌 부분을 자리표시자로 덮는다. 코드 블록, 인라인 코드, URL, 마크다운 링크
   타깃, 표 행, 헤딩이 대상이다. 표 칸은 명사구 나열이라 품사 비율을 왜곡하고, 칸 구분자를
   넘어 매치가 형성되면 표가 깨진다. 오프셋은 그대로 두어 원문에서 스니펫을 다시 잘라낸다.
   큰따옴표 직접 인용은 검출은 하되 교정에서 제외한다.
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
ln -s ~/teammono/tmn-korean-normalizer/skill ~/.claude/skills/korean-normalizer
```

스킬은 전역 설치된 `korean-normalizer`를 호출한다. 설치가 먼저다.

스킬은 CLI로 검출과 기계적 교정을 끝낸 뒤 남은 findings만 LLM이 처리하게 한다.

## 개발

```bash
uv run pytest -q --cov=korean_normalizer
uv run ruff check src tests
uv run ruff format --check src tests
```

## 근거와 출처

- 패턴 정의, S1/S2/S3 심각도, 자연도 등급: [DaleSeo/korean-skills](https://github.com/DaleSeo/korean-skills) (MIT)
- 통계 근거: [KatFishNet, arXiv:2503.00032](https://arxiv.org/abs/2503.00032)
- 형태소 분석기: [kiwipiepy](https://github.com/bab2min/kiwipiepy)
- 맞춤법 규정: [국립국어원 어문규범](https://kornorms.korean.go.kr/regltn/regltnView.do?regltn_code=0001)
