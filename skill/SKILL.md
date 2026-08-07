---
name: korean-normalizer
description: 한국어 텍스트에서 AI 작문 패턴 40가지를 규칙 엔진으로 검출하고 윤문한다. 쉼표 과다, 번역투(에 대해/통해/되어진다/에 있어서), AI 유행어, 결말 관용구, 복수형 과다, 품사 편중 등을 정규식과 통계 지표로 판정하고 자연도 등급 A~D를 매긴다. ChatGPT/Claude/Gemini가 쓴 한국어를 자연스럽게 다듬을 때 사용한다.
license: MIT
allowed-tools: Bash Read Write Edit
---

# korean-normalizer

검출과 기계적 교정은 CLI가 한다. 판단이 필요한 부분만 직접 고친다.

## 1. 검출

```bash
uv run --project ~/repo/tmn-korean-normalizer korean-normalizer detect <파일> --format json
```

출력은 `grade`, `counts`, `findings` 세 부분이다. `findings[].guidance`가 각 패턴의
교정 지침이고, `findings[].samples[]`가 원문 위치와 스니펫이다. 이 목록이 작업 목록이다.

## 2. 기계적 교정

```bash
uv run --project ~/repo/tmn-korean-normalizer korean-normalizer fix <파일> --diff
```

Tier A 9개 규칙(3·6·7·15·17·19·27·31·37)만 적용된다. 의미 판단이 필요 없고
임계를 넘긴 자리에서만 치환하므로 결과를 그대로 받아들여도 된다. 반영하려면
`--diff` 대신 `--in-place`를 쓴다.

## 3. 나머지 윤문

`fix` 이후 다시 `detect`를 돌리면 남은 findings가 직접 고쳐야 할 항목이다.
각 finding의 `guidance`를 따르되 다음을 지킨다.

- 원문의 수치·날짜·고유명사를 그대로 둔다
- 인과 방향과 부정 표현을 뒤집지 않는다
- 큰따옴표 안 직접 인용은 건드리지 않는다
- 원문의 격식 수준을 유지한다

패턴 8~10 띄어쓰기는 검출만 한다. 붙여쓰기로 바꾸면 한글 맞춤법 제42항·제47항을
어기므로 자동 교정 대상이 아니다. 보고만 하고 넘어간다.

패턴 11~13 품사 지표는 kiwipiepy가 설치돼 있을 때만 계산된다. `skipped_metrics`에
해당 지표가 있으면 품사 편중은 판정하지 않았다는 뜻이다.

## 4. 변경률 확인

윤문 후 원본 대비 어절 변경률을 어림한다. 30%를 넘으면 의미 보존을 다시 확인하고,
50%를 넘으면 출력하지 말고 더 보수적으로 다시 쓸지 사용자에게 묻는다.

## 출력 형식

```
자연도 등급: [등급] — [근거 한 줄]
감지 요약: S1 N건, S2 M건, S3 K건

## 자연스러운 버전
[윤문한 텍스트]

## 주요 변경
- [패턴 번호] [무엇을 왜 바꿨는지]
```

## 규칙 목록 확인

```bash
uv run --project ~/repo/tmn-korean-normalizer korean-normalizer rules
```

패턴 정의와 심각도 체계는 [DaleSeo/korean-skills](https://github.com/DaleSeo/korean-skills)의
humanizer 스킬에서 가져왔다. 근거 논문은 [KatFishNet](https://arxiv.org/abs/2503.00032)이다.
