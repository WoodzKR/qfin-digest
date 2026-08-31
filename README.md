# 퀀트 논문 다이제스트 (arXiv + SSRN)

**리포트 보기 → https://woodzkr.github.io/qfin-digest/**

arXiv q-fin.PM/ST/TR 과 SSRN 7개 eJournal 에서 **최근 2개 날짜** 논문을 모아
한국어로 요약하고 HTML 리포트로 만든다. 이미 요약한 논문은 자동으로 건너뛴다.

설계 배경·실측 결과는 [DESIGN.md](DESIGN.md) 참고.

## 준비물

```powershell
npm i -g @anthropic-ai/claude-code     # 요약 엔진
pip install requests playwright pypdf  # SSRN 용
python -m playwright install chromium
```

SSRN 은 Cloudflare 로 막혀 있어 **설치된 Chrome(또는 Edge)** 이 필요하다.
스크립트가 전용 프로필로 Chrome 을 잠깐 띄웠다가 닫으며, 창은 화면 밖에 있어
작업을 방해하지 않는다. arXiv 만 쓸 거면 `--source arxiv` 로 브라우저 없이 돌아간다.

## 사용법

```powershell
cd C:\Users\260165\arxiv-qfin-digest

python run.py                      # 크롤 → 요약 → 리포트 생성 후 브라우저 열기
python run.py --deep 5             # 위와 같되 ★ 상위 5편은 상세 리포트까지 미리 생성
python run.py serve                # 원클릭 모드로 리포트 열기 (아래 참고)

python run.py --source arxiv       # arXiv 만
python run.py --source ssrn        # SSRN 만

python run.py fetch                # 목록 + 초록 수집만
python run.py summarize            # 미요약 논문만 요약
python run.py deep --deep 3        # ★ 상위 3편 상세 리포트만 생성
python run.py report --all         # 누적 전체로 리포트 다시 생성
python run.py status               # 현재 누적 상태
python run.py paper 2608.28399 ssrn-7363482    # 논문별 상세 리포트
```

### 원클릭 모드 — `python run.py serve`

정적 HTML 은 스스로 Claude 를 부를 수 없어서, 원래는 요청 ID 를 복사해 터미널에
붙여넣어야 했다. `serve` 는 `report/` 를 서빙하면서 작은 API 를 얹어 그 왕복을 없앤다.

```powershell
python run.py serve            # http://127.0.0.1:8765 로 열림
```

카드의 `📄 보고서 생성` 을 누르면 바로 생성이 시작되고, 버튼이
`⏳ PDF 받는 중…` → `⏳ 요약 중…` → `📄 상세 리포트 보기` 로 바뀌며 새 탭이 열린다.
생성이 끝나면 다이제스트 HTML 도 자동으로 다시 만들어져 링크가 반영된다.
SSRN 용 Chrome 은 서버가 살아 있는 동안 한 번만 띄워 재사용한다. 종료는 `Ctrl+C`.

서버 없이 파일을 그냥 열거나 GitHub Pages 에서 볼 때는 예전처럼 **명령어 복사** 방식으로
조용히 되돌아간다. 페이지가 `/api/ping` 응답 유무로 알아서 판단한다.
서버에 붙어 있으면 필터 바 오른쪽에 초록색 `로컬 서버 연결됨` 표시가 뜬다.

주요 옵션

| 옵션 | 설명 |
|---|---|
| `--source arxiv\|ssrn\|all` | 대상 출처 (기본 all) |
| `--days N` | 출처별로 가져올 최근 날짜 수 (기본 2) |
| `--workers N` | 요약 동시 실행 수 (기본 3) |
| `--force` | 이미 처리한 논문도 다시 처리 |
| `--all` | `report` 시 날짜 필터 없이 누적 전체 출력 |
| `--no-open` | 생성 후 브라우저를 열지 않음 |
| `--show-browser` | SSRN 용 Chrome 창을 화면에 표시 (디버깅) |
| `--chrome <경로>` | Chrome/Edge 실행 파일 직접 지정 |
| `--deep N` | ★ 상위 N편의 상세 리포트를 미리 생성 |
| `--port N` | `serve` 포트 (기본 8765) |

## 수집 대상

**arXiv** — q-fin.PM(Portfolio Management), q-fin.ST(Statistical Finance),
q-fin.TR(Trading & Market Microstructure). 초록은 arXiv Atom API 에서 받는다.

**SSRN** — 배지 약어로 표시된다.

| 배지 | 저널 |
|---|---|
| QM | Quantitative Methods in Investing & Financial Statement Analysis |
| TI | Technology & Investing |
| GIS | Global Investment Strategy |
| GEX | Global Equities, Exchanges & Investment Indices |
| APV | Capital Markets: Asset Pricing & Valuation |
| MEF | Capital Markets: Market Efficiency |
| MMS | Capital Markets: Market Microstructure |

## 리포트 화면

- **출처 필터** — arXiv / SSRN
- **분야 필터** — PM·ST·TR / QM·TI·GIS·GEX·APV·MEF·MMS (복수 선택, 미선택이면 전체)
- **검색·정렬** — 제목·요약·저자·키워드 검색, ★ 순 정렬
- **논문 카드** — 한 줄 요약 + ★1~5. `자세히` 를 누르면 불릿 3~4개 /
  방법 / 데이터 / 시사점 / **적용도 근거** / 키워드 / 원문 초록

### ★ = 시스템 트레이딩 구현 가능성

연구의 학술적 수준이 아니라 **계량 규칙으로 코딩해 자동매매로 돌릴 수 있는가**만 잰다.

| ★ | 뜻 |
|---|---|
| 5 | 진입·청산 규칙이 명시적이고 공개·표준 데이터만으로 그대로 구현 가능 |
| 4 | 매매 신호·전략 방법론을 제시하고 표준 데이터로 재현 가능. 파라미터는 직접 결정 |
| 3 | 쓸 만한 특징이나 포트폴리오 기법은 주지만 설계를 더 해야 함 |
| 2 | 구현 장벽이 큼 — 위성 사진, 설문, 독점 주문흐름, 초저지연 인프라 등 |
| 1 | 이론·정책·법률·서베이. 자동매매로 옮길 여지 없음 |

통념을 반증하거나, 백테스트 검증 방법론을 개선하거나, 착상이 독창적이면 **+1**.
점수 근거는 카드를 펼치면 `적용도 n/5` 항목에 데이터 확보 난이도와 함께 나온다.
- **버튼** — `원문`, `PDF`, `📄 보고서 생성`

### 보고서 생성 버튼 흐름

| | `serve` 로 열었을 때 | 파일로 열거나 Pages 에서 볼 때 |
|---|---|---|
| 클릭하면 | 바로 생성 시작, 진행 상황이 버튼에 표시되고 끝나면 새 탭으로 열림 | 하단 바에 요청이 쌓임 |
| 그다음 | 없음 | `요청 목록 복사` → 터미널에 붙여넣어 실행 |

전문 확보 방식: arXiv 는 `arxiv.org/html/{id}v1`, SSRN 은 PDF 를 받아 텍스트를 뽑는다.
둘 다 실패하면 초록만으로 만들고 그 사실을 리포트 머리말에 적는다.
수식은 원본 LaTeX 를 살려 MathJax 로 렌더한다.

## Git / GitHub Pages

저장소에는 **코드와 생성물을 함께** 커밋한다. `state/seen.json`(누적 DB)이 같이 올라가야
다른 기기에서 clone 해도 이미 요약한 논문을 건너뛴다.

커밋에서 제외하는 것 (`.gitignore`)

- `state/chrome_profile/` — 150MB 넘는 캐시에 더해 **`cf_clearance` 세션 쿠키가 들어 있다.**
  절대 올리면 안 된다.
- `state/*.bak`, `state/*.tmp`, `__pycache__/`

루트의 `index.html` 은 `report` 명령이 돌 때마다 자동으로 다시 만들어지며,
날짜별 다이제스트와 상세 리포트 목록을 담는다. GitHub Pages 의 진입점이다.

```powershell
python run.py --deep 5 --push   # 수집 → 요약 → 상세 리포트 → 리포트 생성 → 커밋 & push
python run.py publish           # 지금 있는 생성물만 커밋 & push
python run.py publish -m "메모"  # 커밋 메시지 직접 지정
```

`publish` 는 커밋 메시지를 `digest 2026-08-31 — 요약 43편, 상세 리포트 3편` 처럼
자동으로 만든다. push 하고 1~2분이면 Pages 에 반영된다.
`git` 이 PATH 에 없으면 `%LOCALAPPDATA%\Programs\PortableGit` 도 함께 찾는다.

## 파일

```
run.py                 CLI
arxiv_digest/
  config.py            경로·URL·카테고리·SSRN 저널 목록
  listing.py           arXiv /list/{cat}/recent 크롤
  api.py               arXiv Atom API (제목·저자·초록)
  ssrn.py              SSRN 목록 API + Chrome/CDP 초록·PDF 수집
  store.py             seen.json 입출력 (원자적 저장 + .bak)
  summarize.py         claude CLI 호출, JSON 스키마 요약
  paper.py             논문별 심층 리포트 (수식 보존 + MathJax)
  render.py            다이제스트 HTML 렌더링
state/
  seen.json            누적 DB — 이 파일이 중복 요약을 막는다
  chrome_profile/      SSRN 전용 Chrome 프로필 (cf_clearance 쿠키 보관)
report/                생성된 리포트
```

`state/seen.json` 을 지우면 전부 다시 요약한다. 한 논문만 다시 하려면
그 항목의 `summary` 키를 지우고 `python run.py summarize` 를 실행하면 된다.
