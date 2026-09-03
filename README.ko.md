# 퀀트 논문 다이제스트

**[다이제스트 보기 →](https://woodzkr.github.io/qfin-digest/)** · [English](README.md)

arXiv q-fin, SSRN, 실무 블로그 4곳의 새 연구를 한국어와 영어로 요약한다.
한 페이지에서 클릭 한 번으로 언어를 바꾸고, 로그인은 필요 없다.

모든 실행은 내 PC 에서 한다. git 은 완성된 페이지를 배포하는 통로일 뿐이고,
클라우드에서 수집하거나 요약하는 것은 없다.

## 실행하기

```powershell
git clone https://github.com/WoodzKR/qfin-digest
cd qfin-digest
setup.bat      # PC 당 한 번
update.bat     # 새 논문을 받고 싶을 때마다
```

`setup.bat` 은 파이썬 패키지, Chromium, Claude Code CLI 를 설치하고 로그인까지 시킨다.
각 항목을 확인하고 빠진 게 있으면 중간에 실패하는 대신 무엇이 없는지 알려준다.

`update.bat` 이 파이프라인 전체다. 전체 출처 수집 → 신규 요약 → 페이지 재생성 → push.
더블클릭해도 되고 터미널에서 실행해도 된다.

```powershell
update.bat                 # 7개 출처 전부 수집 후 발행
update.bat --deep 3        # 위 + ★ 상위 3편 상세 리포트 미리 생성
update.bat --source ssrn   # 특정 출처만
```

중간에 실패하면 아무것도 발행하지 않고, 수집한 것은 `state/seen.json` 에 남으므로
다시 돌리면 멈춘 지점부터 이어간다.

### 필요한 것

| | |
|---|---|
| Python 3.10+, Node.js | `setup.bat` 이 확인하고 설치 링크를 알려준다 |
| Claude 구독 | 요약 엔진이 Claude Code CLI 다. API 키는 필요 없다 |
| Chrome 또는 Edge | Cloudflare 뒤에 있는 SSRN, Macrosynergy 에만 필요 |

## 상세 리포트

8개 섹션. 본문은 arXiv HTML 판, SSRN PDF, 블로그 아티클에서 가져오고, 다 안 되면
초록만 쓰되 그 사실을 리포트에 적는다. 수식은 원본 LaTeX 를 살려 MathJax 로 렌더한다.

**`report.bat`** 을 더블클릭한다. 로컬 서버가 뜨고 리포트 버튼이 살아 있는 상태로
다이제스트가 열린다. 카드의 `📄 한국어` 나 `📄 English` 를 누르면 그 자리에서 생성된다 —
터미널을 열 필요가 없다. 끝나면 창을 닫고 `update.bat` 으로 발행한다.

생성이 끝나면 버튼이 곧바로 리포트 링크로 바뀌고, 다른 탭을 열어뒀다면 그 탭으로
돌아가는 순간 반영된다. (`python run.py serve` 가 같은 일을 한다.)

정말 읽을 논문이라면 `--review` 를 붙인다. 비평 패스가 논문 전문을 먼저 읽고 —
실제로 기대는 주장, 식별 가정, 타당성 위협, 가장 강한 반론 — 결과·한계 섹션에
반영한다. 편당 약 27분.

```powershell
python run.py paper ssrn-7363482 --lang ko --review
```

한국어는 논문 전체를 한 번에 보면서 처음부터 한국어로 쓴다. 문체 규칙은
[humanize-korean](https://github.com/epoko77-ai/im-not-ai) 의 택소노미에서 뽑아
생성 프롬프트에 넣었다. 별도 윤문 단계는 두지 않는다 — 완성된 조각만 보는 윤문기는
섹션 사이 용어를 일관되게 유지하지 못한다.

## 명령어

보통은 `update.bat` 이면 된다. 그 아래는 이렇다.

```powershell
python run.py                  # 수집 → 요약 → 페이지 생성 후 열기
python run.py fetch            # 수집만
python run.py summarize        # 요약이 빠진 것만 요약
python run.py report --all     # 페이지 재생성
python run.py publish          # 커밋 & push
python run.py status           # 현재 누적 상태
```

| 옵션 | |
|---|---|
| `--source` | `all`, 출처 하나, 또는 목록: `arxiv,quantpedia,man` |
| `--lang` | `ko` / `en` / `both` — 상세 리포트 언어 |
| `--deep N` | ★ 상위 N편 상세 리포트를 미리 생성 |
| `--days N` | 논문 출처별 최근 날짜 수 (기본 2) |
| `--review` | 상세 리포트를 쓰기 전 비평 패스 |
| `--stale` | 구버전 프롬프트가 만든 것만 다시 처리 |
| `--force` | 이미 처리한 것도 다시 처리 |
| `--push` | 전체 실행 후 발행 |

### 프롬프트를 바꿨을 때

기존 결과물은 자동으로 다시 만들어지지 않는다 — 문구 하나 고쳤다고 100번 호출이
돌면 곤란하다. 요약과 리포트마다 어떤 프롬프트가 만들었는지 기록하고,
`run.py status` 가 현황을 보여준다.

```
current prompts — summary 2026-09-01, report 2026-09-01
  summaries   : 2026-09-01 100
  deep reports: 2026-09-01 8
  everything is on the current prompts
```

옛 결과물에도 적용할 만한 변경이면 `arxiv_digest/config.py` 의 `SUMMARY_VERSION`
이나 `REPORT_VERSION` 을 올리고 `--stale` 로 안 맞는 것만 다시 돌린다. 둘은 서로
독립이라, **상세 리포트 프롬프트를 바꿔도 요약은 건드리지 않는다.**

## 수집 대상

| | 출처 | "최근"의 기준 |
|---|---|---|
| arXiv | q-fin.PM, q-fin.ST, q-fin.TR | 카테고리별 최근 2개 게시일 |
| SSRN | 6개 eJournal — QM, GIS, GEX, APV, MEF, MMS | 저널별 최근 2개 승인일 |
| 블로그 | Quantpedia, Alpha Architect, Macrosynergy, Quantocracy | 각 최근 8개 글 |

Quantocracy 는 모음집이라, 직접 수집하는 사이트와 겹치는 항목은 버린다.

Man Group 과 SSRN 의 *Technology & Investing* 은 점수를 매겨 본 뒤 제외했다. Man Group 은
17건 전부, TI 는 23건 중 18건이 ★1이었다. 둘 다 제대로 된 글을 내지만 — 매크로 논평과
비금융 기술 연구 — 이 도구가 잴 수 있는 대상이 아니라 평균과 정렬만 끌어내렸다.

## ★ 점수

★ 는 **시스템 트레이딩으로 옮길 수 있는가**를 잰다. 학술적 수준이 아니다.

| ★ | |
|---|---|
| 5 | 진입·청산 규칙이 명시적이고 공개·표준 데이터만으로 그대로 백테스트 가능 |
| 4 | 신호나 방법론을 주고 표준 데이터로 재현 가능. 파라미터는 직접 결정 |
| 3 | 쓸 만한 특징이나 포트폴리오 기법은 주지만 설계를 더 해야 함 |
| 2 | 장벽이 큼 — 위성 사진, 설문, 독점 주문흐름, 초저지연 |
| 1 | 이론·정책·법률·서베이. 자동매매로 옮길 여지 없음 |

통념을 반증하거나, 백테스트 방법론을 개선하거나, 착상이 독창적이면 **+1**.
데이터를 구할 수 없으면 2 이하로 묶인다. 모든 점수에는 **필요한 데이터를 명시한**
한 줄 근거가 붙는다. 카드를 펼치면 보인다.

## 배포

`state/seen.json` 을 생성된 페이지와 함께 커밋한다. 이 파일이 같은 논문을 두 번
요약하지 않게 막으므로, 다른 PC 에서 clone 하면 이어서 작업할 수 있다. 루트의
`index.html` 이 GitHub Pages 진입점이고 실행할 때마다 다시 만들어진다.

`state/chrome_profile/` 은 절대 커밋하지 않는다 — `cf_clearance` 세션 쿠키가 들어 있다.
`.gitignore` 에 이미 들어가 있다.

---

[DESIGN.md](DESIGN.md) — 동작 방식 · [NOTES.md](NOTES.md) — 결정 기록과 막다른 길
