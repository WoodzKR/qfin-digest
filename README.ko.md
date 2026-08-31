# 퀀트 논문 다이제스트 — arXiv q-fin + SSRN

**[English README](README.md)** · **[리포트 보기 →](https://woodzkr.github.io/qfin-digest/)**

arXiv q-fin.PM/ST/TR, SSRN 7개 eJournal, 그리고 실무 블로그 5곳에서 새 글을 모아
로컬 Claude Code CLI 로 **한국어와 영어 양쪽** 요약을 만들고, 외부 의존이 없는 HTML
다이제스트 한 장으로 뽑는다. 이미 요약한 것은 다음 실행에서 건너뛴다.

설계는 [DESIGN.md](DESIGN.md), 결정 기록과 막다른 길은 [NOTES.md](NOTES.md) 참고.

## 준비물

```powershell
npm i -g @anthropic-ai/claude-code     # 요약 엔진
pip install requests playwright pypdf  # SSRN 용
python -m playwright install chromium
```

SSRN 은 Cloudflare 뒤에 있어 **설치된 Chrome(또는 Edge)** 이 필요하다. 스크립트가
전용 프로필로 Chrome 을 띄웠다 닫으며, 창은 화면 밖에 있어 작업을 방해하지 않는다.
`--source arxiv` 로 돌리면 파이썬만 있으면 된다.

## 사용법

```powershell
python run.py                      # 수집 → 요약 → 리포트 생성 후 브라우저 열기
python run.py --deep 5             # 위와 같되 ★ 상위 5편은 상세 리포트까지 미리 생성
python run.py serve                # 원클릭 모드 (아래 참고)

python run.py --source arxiv       # arXiv 만
python run.py --source ssrn        # SSRN 만

python run.py fetch                # 목록 + 초록 수집만
python run.py summarize            # 요약이 빠진 논문만 요약
python run.py deep --deep 3        # ★ 상위 3편 상세 리포트만 생성
python run.py report --all         # 누적 전체로 리포트 다시 생성
python run.py status               # 현재 누적 상태
python run.py paper 2608.28399 --lang en
python run.py publish              # 생성물 커밋 & push
```

| 옵션 | 설명 |
|---|---|
| `--source` | `all`(기본), 출처 하나, 또는 목록: `arxiv,quantpedia,man` |
| `--blog-limit N` | 블로그별 최근 N개 글 (기본 8) |
| `--lang ko\|en\|both` | 상세 리포트 언어 (기본 `ko`) |
| `--days N` | 출처별로 가져올 최근 날짜 수 (기본 2) |
| `--workers N` | 요약 동시 실행 수 (기본 3) |
| `--deep N` | ★ 상위 N편의 상세 리포트를 미리 생성 |
| `--force` | 이미 처리한 것도 다시 처리 |
| `--all` | 리포트를 오늘치가 아닌 누적 전체로 |
| `--push` | `all` 실행 후 커밋 & push |
| `--port N` | `serve` 포트 (기본 8765) |
| `--no-open` | 브라우저를 열지 않음 |
| `--show-browser` | SSRN 용 Chrome 창을 화면에 표시 |
| `--chrome <경로>` | Chrome/Edge 실행 파일 직접 지정 |

### 원클릭 모드 — `python run.py serve`

정적 HTML 은 스스로 Claude 를 부를 수 없어서, 파일로 열면 명령어를 복사해 터미널에
붙여넣는 왕복이 생긴다. `serve` 는 `report/` 를 서빙하면서 작은 API 를 얹어 그 왕복을 없앤다.

```
📄 한국어 / 📄 English  →  ⏳ PDF 받는 중…  →  ⏳ 리포트 작성 중…  →  📄 (새 탭)
```

생성이 끝나면 다이제스트 HTML 도 자동으로 다시 만들어지고, SSRN 용 Chrome 은 서버가
살아 있는 동안 한 번만 띄워 재사용한다. 파일로 열거나 GitHub Pages 에서 볼 때는
`api/ping` 응답이 없으니 예전 복사 방식으로 조용히 되돌아간다. 지금 어느 모드인지는
초록색 `로컬 서버 연결됨` 표시로 알 수 있다.

## 수집 대상

**arXiv** — q-fin.PM(Portfolio Management), q-fin.ST(Statistical Finance),
q-fin.TR(Trading & Market Microstructure). 초록은 arXiv Atom API 에서 받는다.

**SSRN** — 카드에 배지로 표시된다.

| 배지 | eJournal |
|---|---|
| QM | Quantitative Methods in Investing & Financial Statement Analysis |
| TI | Technology & Investing |
| GIS | Global Investment Strategy |
| GEX | Global Equities, Exchanges & Investment Indices |
| APV | Capital Markets: Asset Pricing & Valuation |
| MEF | Capital Markets: Market Efficiency |
| MMS | Capital Markets: Market Microstructure |

**블로그** — 논문이 아니라 실무자 글이라 "최근 2개 날짜" 대신 **최근 N개 글**로 가져온다.

| 배지 | 사이트 | 방식 |
|---|---|---|
| QP | [Quantpedia](https://quantpedia.com/blog/) | RSS 피드 |
| MAN | [Man Group Insights](https://www.man.com/insights) | 목록 페이지 + 글마다 1회 요청 |
| AA | [Alpha Architect](https://alphaarchitect.com/blog/) | RSS 피드 (블로그 페이지는 Cloudflare 로 막힘) |
| MS | [Macrosynergy](https://macrosynergy.com/research/blog/) | Chrome 으로 Cloudflare 통과 후 RSS 피드 |
| QC | [Quantocracy](https://quantocracy.com/) | 홈페이지의 큐레이션 링크 목록 파싱 |

Quantocracy 는 모음집이라 위 사이트들과 겹친다. 직접 수집하는 사이트를 가리키는 항목은
버리고 직접 수집한 쪽을 남긴다 — Quantocracy 는 발췌를 `(...)` 로 자르지만 원본 피드는
전문을 준다. 저장소도 정규화한 URL 로 대조해서, 이전에 `--source` 를 좁게 잡고 돌렸을 때
들어온 중복까지 걷어낸다.

## 리포트 화면

- **언어 전환** — 한국어 / English. 두 언어가 페이지에 함께 들어 있어 즉시 바뀐다.
- **필터** — 출처(arXiv / SSRN), 분야(PM·ST·TR, QM·TI·GIS·GEX·APV·MEF·MMS),
  제목·요약·저자·키워드 검색.
- **카드** — 한 줄 요약 + ★1~5. 펼치면 불릿 3~4개, 방법, 데이터, 트레이딩 적용,
  점수 근거, 키워드, 원문 초록.
- **버튼** — `abs`, `PDF`, 그리고 언어별 상세 리포트 버튼.

### ★ = 시스템 트레이딩 구현 가능성

연구의 학술적 수준이 아니라 **계량 규칙으로 코딩해 자동매매로 돌릴 수 있는가**만 잰다.

| ★ | 뜻 |
|---|---|
| 5 | 진입·청산 규칙이 명시적이고 공개·표준 데이터만으로 그대로 백테스트 가능 |
| 4 | 신호나 전략 방법론을 제시하고 표준 데이터로 재현 가능. 파라미터는 직접 결정 |
| 3 | 쓸 만한 특징이나 포트폴리오 기법은 주지만 설계를 상당히 더 해야 함 |
| 2 | 구현 장벽이 큼 — 위성 사진, 설문, 독점 주문흐름, 초저지연 인프라 |
| 1 | 이론·정책·법률·서베이. 자동매매로 옮길 여지 없음 |

통념을 반증하거나, 백테스트 검증 방법론을 개선하거나, 착상이 독창적이면 **+1**.
데이터를 구할 수 없으면 결과가 아무리 좋아도 2 이하다. 모든 점수에는
**데이터 확보 난이도를 반드시 언급한** 한 줄 근거가 붙는다. 카드를 펼치면 보인다.

## 상세 리포트

8개 섹션: 한눈에 보기, 문제의식, 방법론, 데이터와 실험 설계, 주요 결과, 한계,
시스템 트레이딩 적용 아이디어, 함께 볼 만한 개념.

본문은 arXiv HTML 판이나 SSRN PDF 에서 가져온다. 둘 다 실패하면 초록만 쓰고 그 사실을
리포트에 적는다. 수식은 원본 LaTeX 를 살려 MathJax 로 렌더한다 — arXiv 의
`<math alttext="...">` 를 태그 제거 **전에** 복원하므로 첨자가 뭉개지지 않는다.

파일은 `report/paper/{id}.{lang}.html` 로 떨어진다.

## Git 과 GitHub Pages

**코드와 생성물을 함께** 커밋한다. `state/seen.json` 이 같이 가야 다른 기기에서
clone 했을 때 전부 다시 요약하지 않는다.

`.gitignore` 로 제외하는 것

- `state/chrome_profile/` — 150MB 캐시에 더해 **`cf_clearance` 세션 쿠키**가 들어 있다.
  절대 올리면 안 된다.
- `state/*.bak`, `state/*.tmp`, `__pycache__/`

루트의 `index.html` 은 `report` 명령이 돌 때마다 다시 만들어지며 GitHub Pages 진입점이다.

```powershell
python run.py --deep 5 --push   # 수집 → 요약 → 상세 리포트 → 리포트 → push
python run.py publish           # 지금 있는 생성물만 올리기
python run.py publish -m "메모"
```

`publish` 는 `digest 2026-08-31 — 59 summaries, 6 reports` 같은 커밋 메시지를 자동으로
만든다. push 하고 1~2분이면 Pages 에 반영된다. `git` 이 PATH 에 없으면
`%LOCALAPPDATA%\Programs\PortableGit` 도 함께 찾는다.

## 내 컴퓨터가 꺼져 있어도 웹에서 업데이트하기

`.github/workflows/update-digest.yml` 이 전체 파이프라인을 GitHub 서버에서 돌린다.

- **Actions → Update digest → Run workflow** 버튼으로 수동 실행. 휴대폰에서도 눌린다.
- 스케줄로도 돈다: 평일 오전 6시(KST).
- 입력값으로 출처, 날짜 수, 상세 리포트 개수, 언어를 고를 수 있다.

최초 1회 설정 — 요약 엔진이 Claude Code CLI 인데 CI 러너에는 대화형 로그인이 없어서
**Settings → Secrets and variables → Actions** 에 인증 수단을 등록해야 한다. 둘 중 하나면 된다.

| 시크릿 | 발급 방법 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | 로컬에서 `claude setup-token` 을 돌려 나온 값을 붙여넣는다. Claude 구독을 그대로 쓰므로 **API 키가 필요 없다.** 이쪽을 권한다. |
| `ANTHROPIC_API_KEY` | 종량제 API 키. 위 토큰이 없을 때만 쓰인다. |

이 워크플로는 `workflow_dispatch` 와 `schedule` 로만 돈다. fork 에서 올린 PR 은
시크릿에 접근할 수 없다.

알아둘 점 두 가지

- **그 버튼은 쓰기 권한이 있는 사람만 누를 수 있다.** GitHub 은 익명 방문자에게
  워크플로 실행을 열어주지 않는다. 다른 사람이 쓰고 싶으면 fork 하거나 clone 해서
  직접 돌리면 되고, 아래 빠른 시작이 그 용도다.
- **CI 에서 SSRN 은 될 수도 안 될 수도 있다.** Cloudflare 가 데이터센터 IP 를 거의
  막기 때문에 기본 출처는 `arxiv,quantpedia,man` 이다. SSRN 을 켜도 막히면 그 소스만
  건너뛰고 나머지는 정상 수집된다.

## 다른 사람이 자기 컴퓨터에서 돌리려면

```powershell
git clone https://github.com/WoodzKR/qfin-digest
cd qfin-digest
pip install requests playwright pypdf
python -m playwright install chromium
npm i -g @anthropic-ai/claude-code
claude login          # 또는 ANTHROPIC_API_KEY 환경변수

python run.py --source arxiv,quantpedia,man   # 브라우저 없이 동작
python run.py serve                            # 원클릭 상세 리포트
```

`state/seen.json` 이 clone 에 함께 오므로 이미 요약된 것을 다시 요약하지 않는다.
Chrome 이 있으면 `--source all` 로 SSRN 까지 포함한다.

## 파일 구조

```
run.py                 CLI
arxiv_digest/
  config.py            경로·엔드포인트·카테고리·저널 표
  listing.py           arXiv /list/{cat}/recent 크롤
  api.py               arXiv Atom API
  ssrn.py              SSRN 목록 API + Chrome/CDP 초록·PDF 수집
  store.py             seen.json 입출력, 원자적 저장, 스키마 마이그레이션
  summarize.py         claude CLI 호출, 이중 언어 JSON 스키마
  paper.py             상세 리포트, 수식 보존
  render.py            다이제스트·인덱스 렌더링
  server.py            로컬 원클릭 서버
state/
  seen.json            누적 DB — 이 파일이 중복 요약을 막는다
  chrome_profile/      SSRN Chrome 프로필 (cf_clearance 보관, 커밋 제외)
report/                생성된 리포트
```

`state/seen.json` 을 지우면 전부 다시 요약한다. 한 논문만 다시 하려면 그 항목의
`summary` 키를 지우고 `python run.py summarize` 를 실행하면 된다.
