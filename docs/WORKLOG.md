# Castlevania Dominus Collection 한글화 작업 전체 내역

기간: 2026-07-05 ~ 2026-07-06 (Codex 세션 "분석하기"를 이어받아 진행)
대상: `C:\CHRONOS Releases\Castlevania Dominus Collection\windata\alldata.bin` (853MB)

---

## 1단계 — 메시지 인코딩 구조 해석 (7/5)

Codex가 멈춘 지점("코드값→문자 매핑 테이블 만들기")을 이어받아 완성.

| 발견 | 내용 |
|---|---|
| 폰트 내장 코드 | `LD937714*.DAT` 레코드(26B) = [SJIS코드 2B][12행×2B 비트맵]. 오름차순 코드 체인 스캔으로 문자집합 추출 가능 |
| dense rank 코드 | 메시지 토큰 = 문자집합(SJIS 정렬 부분집합)의 순번을 SJIS식 lead/trail(행당 188)로 인코딩 |
| 회전(rotation) | 폰트 레코드 = (rank+666) mod 1217 (Dra01 큰폰트). 도달불가 40슬롯 = 플랫폼별 버튼 그래픽 |
| 검증 | seed 41자 전수 일치, Dra01 1177자/Dra02 1339자 매핑 누락 0 |

산출: `outputs/dra01_dialogue/`, `outputs/dra02_dialogue/` (코드표 + 일본어 전문 TSV/JSON),
`outputs/MessageCodeMapping.md`, `work/claude_mapping/build_mapping.py`

## 2단계 — 한글패치 재구축·적용 (7/5)

기존 패치 exe(Dra01/Dra02KoreanV3-0.exe)가 깨졌던 원인 3가지를 규명:

1. **메시지 오프셋 +0x3800 어긋남** — 구버전 message.psb 내부 배치 기준의 절대주소 사용
   (Dra02 LinkMap 1852개 전부가 -0x3800 보정 시 엔트리 경계와 정확히 일치함을 증명)
2. **폰트 회전 무시** — DAT 파일 선두부터 순차 덮어씀
3. **레코드 내장 코드 파괴** — 글자 위 잡음의 원인

재구축 방법: 원본(`alldata-원본.bin`)에서 시작, 패치 리소스의 한국어 번역(레코드 r = rank r)을
올바른 위치에 기록. 비트맵만 교체(코드 보존), wrap 슬롯은 미사용 rank로 토큰 리매핑.
NX/PS5/WIN 3개 플랫폼 변형을 각자 구조에 맞게 처리(WIN 큰폰트 = 한자 26B + 전체 8×8 이중 구조).
총 12,594건 기록, 전 기록의 허용영역 검사 통과. 패치 후 렌더링 전수 검증 → `alldata.bin` 교체.

산출: `outputs/KoreanPatchRebuild.md`, `work/claude_mapping/build_korean_patch.py`, `verify_build.py`

## 3단계 — Dra03(오더 오브 에클레시아) 구조 해석 (7/6)

- **공식 한국어 발견**: 언어 키에 `ko`(=resource#1) 존재. 팬패치가 Dra03을 뺀 이유로 추정
- 위치: message.psb @0x230A5800, ja @0x230A597E(143,723B), ko @0x230C8AE9(157,211B), 1927엔트리
- ko 텍스트 = **raw EUC-KR(cp949)** — dense 변환 불필요
- 한글 폰트 `LC_KOR12`(@0x2233BFD0, 80,528B): 24B/글리프, 심볼 959개 + **KS 완성형 2350자 전체**,
  글리프 공식 `959 + (lead-0xB0)*94 + (trail-0xA1)` (실측 검증)
- `LC_KOR8`(8px) = 버튼 아이콘+ASCII만 → 8px로 그려지는 HUD 라벨은 한글 불가
- 일어 폰트 LD937714 = 회전 없는 선형 1455자 (신형 구조)

## 4단계 — 대사 편집 파이프라인 구축 (7/6)

`pipeline/` : `extract.py`(추출) → TSV 편집 → `insert.py`(재삽입)

- TSV: index / reference(일본어) / text(편집 대상), 제어코드는 `<F006>` 태그로 왕복 보존
- dra01/02 인코딩용 **한글 글리프↔문자 식별표** 구축: 굴림 템플릿 매칭 + "rank순=가나다순"
  단조성 DP + 앵커(육안 확정) → `work/claude_mapping/{game}_rank_to_hangul.tsv`
- 폰트에 없는 한글 → 여유 슬롯에 굴림체 12×12/8×8 글리프 자동 생성·주입
- dra01 패치 테이블이 비단조(문자열 공유)임을 발견 → 파서를 F00A 종결자 기준으로 설계,
  재조립 시 동일 문장 자동 공유. 토큰 0xXX7F ≡ 0xXX80 별칭 확인
- 검증: 무수정 라운드트립(dra03 바이트 동일, dra01/02 의미 동일) + 실수정 테스트
  (신규 글자 '퀭' 자동 생성 포함) 통과

## 5단계 — 전면 번역 개선 (7/6)

### dra03 영문 고유명사 한글화
- 번역 대상 575종 확정 (`pipeline/dra03_names_ko.py`): 인명 18, 글리프 주문 ~110,
  아이템/장비 ~240, 적 ~120, 지명 ~30, BGM 일본어 제목 ~75
- 이름 엔트리 613개 전체 치환 + 대사 속 언급 451건 치환
- 유지 96종: HUD 라벨(LV/EXP/ATK/메뉴명)과 영문 원제 BGM — 8px ASCII 폰트 제약
- 원복 스냅샷: `pipeline/text/dra03_ko.tsv.english-names`
- 효과: ko 리소스 12,889바이트 여유 확보(영문보다 짧아짐)

### 식별표 전수 감사 (dra01 830 rank / dra02 912 rank)
- rank별 사용 단어 문맥 감사로 dra02 식별 오류 ~50건 교정
  (겨/격, 군/굳/굴, 문/묻/물, 까, 귀, 깨, 꺼, 께, 껴, 꾀, 끼, 너, 디, 떠/떤, 뚜, 류, 속, 송,
  쇄, 순, 씌, 육/율, 잃, 잌, 쥐, 쥬, 짧, 최, 커, 켜, 튜, 티, 푸/푼, 퓨, 협, 히 등)
- dra01 테이블은 무결 확인 (dra01 폰트가 굴림계라 자동 매칭 정확도가 높았음)
- 제작자 버그 수정: 텍스트가 참조하는데 한자가 남아있던 슬롯(dra02 콤·맨, dra01 휘)에
  올바른 글리프 주입

### 미번역 번역 + 오타 수정
- dra02 #1808 자매모드 터치 조작설명(완전 미번역) 신규 번역
- dra02 #1861 표정 라벨 37종 번역 (보통/미소/분노/시무룩/뾰로통 등)
- dra02 #372/385/608 잔존 일본어 정리
- 원 패치 오타: 침흑→칠흑(dra01, 신규 글리프), 어떤한→어떠한, 방항→방황, 벗어나기기→벗어나기,
  맛있는버럿→버섯, 납든/한가든/획든/취든→득, 시킷→시킴×3, 어떻하지→어떡하지, 알댄테→알덴테
- 신규 글리프 총 7자 생성·주입: 퀭(테스트), 칠, 덴, 떡, 뾰, 쁨, 칫

## 백업 체계

| 파일 | 내용 |
|---|---|
| `alldata-원본.bin` | 순정 원본 (불변) |
| `alldata.before-claude-korean-20260705.bin` | 재구축 배포 직전(Codex 실험 상태) |
| `alldata.backup-20260706-092917.bin` | 번역 개선 직전(재구축판) |
| `alldata.bin` | **현재: 재구축 + 번역 개선판** |
| `pipeline/text/dra03_ko.tsv.english-names` | dra03 이름 영문 원복용 스냅샷 |

## 인게임 확인 필요 사항

1. dra01/02: 일본어 언어 설정에서 대사/메뉴 한글 표시 (재구축분)
2. dra03: 한국어 설정에서 **아이템·글리프 메뉴의 한글 이름** 표시 여부
   → 깨지면: `copy pipeline\text\dra03_ko.tsv.english-names pipeline\text\dra03_ko.tsv`
   후 `python pipeline\insert.py dra03`
3. PC빌드가 WIN 폰트 변형을 쓸 경우 일부 소형 텍스트 확인 (WIN 전용 소폰트는 미해독으로 원본 유지)
