# 퀀트 논문 다이제스트

**[다이제스트 보기 →](https://woodzkr.github.io/qfin-digest/)** · [English](README.md)

arXiv q-fin, SSRN, 실무 블로그 5곳의 새 연구를 한국어와 영어로 요약한다.
한 페이지에서 클릭 한 번으로 언어를 바꾸고, 로그인은 필요 없다.

| | |
|---|---|
| **읽기만 할 때** | 위 링크를 열면 된다. 설치할 것 없음. |
| **어느 기기에서든 갱신할 때** | [워크플로 실행](#어디서든-갱신하기) — 버튼 하나, 로컬 설정 불필요. |
| **직접 돌릴 때** | [내 PC에 설치](#내-pc에서-돌리기). |

---

## 어디서든 갱신하기

**[Actions → Update digest → Run workflow](https://github.com/WoodzKR/qfin-digest/actions/workflows/update-digest.yml)**

GitHub 서버에서 돌기 때문에 내 컴퓨터는 꺼져 있어도 된다. 휴대폰에서도 눌린다.
평일 오전 6시(KST)에는 자동으로도 돈다.

입력값은 출처, 최근 날짜 수, 상세 리포트 개수, 언어. 기본값 그대로 두면 된다.

저장소 소유자로 로그인해야 버튼이 보인다. GitHub 은 방문자에게 워크플로 실행을 열어주지
않는다. 남이 돌리고 싶으면 fork 해서 자기 인증 수단을 쓰면 된다.

<details>
<summary>최초 1회 설정 (이 저장소는 완료됨)</summary>

**Settings → Secrets and variables → Actions** 에 둘 중 하나를 등록한다.

| 시크릿 | 발급 방법 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` — Claude 구독을 그대로 쓴다. API 키 불필요 |
| `ANTHROPIC_API_KEY` | 종량제 API 키. 위 토큰이 없을 때만 쓰인다 |

기본 출처에서 SSRN 은 빠져 있다. Cloudflare 가 데이터센터 IP 를 거의 막기 때문이다.
다시 켜도 막히면 그 소스만 건너뛰고 나머지는 정상 수집된다.
</details>

## 내 PC에서 돌리기

```powershell
git clone https://github.com/WoodzKR/qfin-digest
cd qfin-digest

pip install requests playwright pypdf
python -m playwright install chromium
npm i -g @anthropic-ai/claude-code
claude login

python run.py --source arxiv,quantpedia,man,alphaarchitect,macrosynergy,quantocracy
python run.py serve      # http://127.0.0.1:8765 에서 상세 리포트 원클릭
```

SSRN 은 Chrome 이나 Edge 가 추가로 필요하다. 설치돼 있으면 `--source all` 로 켠다.
`state/seen.json` 이 clone 에 함께 오므로 이미 요약된 것을 다시 요약하지 않는다.

내 저장소로 발행하려면 `python run.py publish`.

## 명령어

```powershell
python run.py                  # 수집 → 요약 → 페이지 생성 후 열기
python run.py --deep 5 --push  # 위 + ★ 상위 5편 상세 리포트 + 발행
python run.py serve            # 원클릭 모드
python run.py status           # 현재 누적 상태
python run.py paper <id> --lang en
```

| 옵션 | |
|---|---|
| `--source` | `all`, 출처 하나, 또는 목록: `arxiv,quantpedia,man` |
| `--lang` | `ko` / `en` / `both` — 상세 리포트 언어 |
| `--deep N` | ★ 상위 N편 상세 리포트를 미리 생성 |
| `--days N` | 논문 출처별 최근 날짜 수 (기본 2) |
| `--review` | 상세 리포트를 쓰기 전 비평 패스 (호출 1회 추가) |
| `--force` | 이미 처리한 것도 다시 처리 |
| `--push` | 전체 실행 후 발행 |

## 수집 대상

| | 출처 | "최근"의 기준 |
|---|---|---|
| arXiv | q-fin.PM, q-fin.ST, q-fin.TR | 카테고리별 최근 2개 게시일 |
| SSRN | 7개 eJournal — QM, TI, GIS, GEX, APV, MEF, MMS | 저널별 최근 2개 승인일 |
| 블로그 | Quantpedia, Man Group, Alpha Architect, Macrosynergy, Quantocracy | 각 최근 8개 글 |

Quantocracy 는 모음집이라, 직접 수집하는 사이트와 겹치는 항목은 버린다.

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

## 상세 리포트

8개 섹션. 본문은 arXiv HTML 판, SSRN PDF, 블로그 아티클에서 가져오고, 다 안 되면
초록만 쓰되 그 사실을 리포트에 적는다. 수식은 원본 LaTeX 를 살려 MathJax 로 렌더한다.

한국어 리포트는 논문 전체를 한 번에 보면서 처음부터 한국어로 쓴다. 문체 규칙은
[humanize-korean](https://github.com/epoko77-ai/im-not-ai) 의 택소노미에서 뽑아
생성 프롬프트에 넣었다. 별도 윤문 단계는 두지 않는다 — 완성된 조각만 보는 윤문기는
섹션 사이 용어를 일관되게 유지하지 못한다.

`--review` 를 붙이면 먼저 비평 패스가 돈다 — 논문이 실제로 기대는 주장, 식별 가정,
타당성 위협, 가장 강한 반론을 뽑아 결과·한계 섹션에 반영한다. 이 패스는 논문 전문을
읽으므로 윤문기에 없던 문맥을 갖는다.

---

[DESIGN.md](DESIGN.md) — 동작 방식 · [NOTES.md](NOTES.md) — 결정 기록과 막다른 길
