# Dominus Collection 대사 편집 파이프라인

세 게임의 대사를 **추출 → 수정 → 재삽입**하는 도구.
대상 파일: `C:\CHRONOS Releases\Castlevania Dominus Collection\windata\alldata.bin`

| 게임 | 내용 | 텍스트 인코딩 |
|---|---|---|
| dra01 | 창월의 십자가 (팬 한글패치 적용본) | dense rank 토큰 + 한글표 |
| dra02 | 빼앗긴 각인 (팬 한글패치 적용본) | dense rank 토큰 + 한글표 |
| dra03 | 오더 오브 에클레시아 (**공식 한국어**) | raw EUC-KR(cp949) |

## 사용법

```bat
cd C:\Users\Jay\Documents\Codex\2026-07-04\qn

:: 1) 추출 — pipeline\text\{게임}_ko.tsv 생성
python pipeline\extract.py dra01 dra02 dra03

:: 2) 수정 — TSV의 'text' 열만 편집 (엑셀 가능, 탭 구분/UTF-8 유지)
::    reference 열 = 일본어 원문 (참고용, 무시됨)

:: 3) 삽입 — 자동 백업 후 alldata.bin에 기록
python pipeline\insert.py dra01 dra03
```

## TSV 편집 규칙

- `<F006>` = 줄바꿈, `<F00A>` = 엔트리 종결(지우지 말 것), `<F007><00xx>` = 화자/창 제어,
  `<0000>` = 엔트리 시작 파라미터. **태그는 그대로 두고 사이의 글만 수정**.
- 반각 공백/영숫자는 자동으로 전각 변환됨. 전각 구두점(。、？！…) 그대로 사용 가능.
- dra03: KS X 1001 완성형 한글 2350자 전부 사용 가능 (똠, 뷁 등 확장 음절은 불가).
- dra01/02: 폰트에 없는 한글이 나오면 **자동으로 여유 슬롯에 굴림체 글리프를 생성·주입**
  (dra01 여유 93슬롯, dra02 180슬롯). 신규 글자는 `work/claude_mapping/*_rank_to_hangul.tsv`에 자동 기록.
- 길이 제한: 엔트리별 제한은 없고 **리소스 전체 크기**가 예산
  (dra01 여유 ~500B, dra02 ~1.3KB, dra03 ~1.8KB + 동일 문장 공유로 절약됨).
  초과하면 삽입이 거부되고 몇 바이트 줄여야 하는지 알려줌.
- 화면 폭: 대화창 기준 한 줄 전각 약 15~16자. 길면 `<F006>`으로 줄바꿈.

## 주의

- `insert.py`는 실행 시 `alldata.backup-<시각>.bin` 백업을 만든다 (`--no-backup`으로 생략).
- 미번역(일본어 잔존) 엔트리의 한자 태그(`<t:XXXX>`)와 원문 토큰은 그대로 보존됨.
- 게임 언어 설정: dra01/02 한국어는 **일본어 언어**로 플레이(jp_ja 교체본),
  dra03 공식 한국어는 언어 설정의 한국어 그대로.

## 내부 문서

- 구조 해석: `outputs/MessageCodeMapping.md`, `outputs/KoreanPatchRebuild.md`
- 글리프↔문자 표: `work/claude_mapping/dra01_rank_to_hangul.tsv`, `dra02_...tsv`
- 검수 시트: `work/claude_mapping/dra01_review.png`, `dra02_review.png`
- Dra03 구조: message.psb @0x230A5800 (ja=res#0 @0x230A597E, ko=res#1 @0x230C8AE9,
  1927엔트리), 한글폰트 LC_KOR12(12px, KS순 2350자 전부, record=24B 비트맵,
  glyph = 959 + (lead-0xB0)*94 + (trail-0xA1)) @0x2233BFD0(NX),
  일어폰트 LD937714(선형 1455자) @0x2237AD40(NX)
- 번역 개선(2026-07-06): dra03 고유명사 한글화(613엔트리+대사 언급 451건,
  확정표=pipeline/dra03_names_ko.py, 영문 원복 스냅샷=text/dra03_ko.tsv.english-names),
  dra01/02 식별표 전수 감사(오류 ~50건 수정), 미번역 번역(dra02 1808/1861 등),
  오타 수정(칠흑/어떠한/커맨드/까마귀 등). HUD 라벨(LV/EXP/ATK...)과 영문 원제
  BGM은 8px ASCII 폰트 제약으로 영문 유지.
