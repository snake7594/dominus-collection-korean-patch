# 캐슬바니아 도미누스 컬렉션 한글패치 (Castlevania Dominus Collection — Korean Translation Patch)

**대상:** Castlevania Dominus Collection (PC) — `windata\alldata.bin`
**형식:** xdelta3 (VCDIFF) · **버전:** v1

컬렉션에 수록된 NDS 3부작을 한국어화하는 **비공식 팬 패치**입니다.

| 게임 | 내용 |
|---|---|
| 창월의 십자가 (Dawn of Sorrow) | 기존 NDS 팬 한글패치의 번역을 컬렉션 구조에 맞게 **재이식** + 오타 수정 |
| 빼앗긴 각인 (Portrait of Ruin) | 위와 동일 + 미번역 구간 신규 번역 |
| 오더 오브 에클레시아 (Order of Ecclesia) | **공식 한국어**의 영문 고유명사(인명/아이템/마법/지명 등 1,000여 곳)를 한글 표기로 개선 |

> ⚠️ **이 저장소에는 게임 데이터가 들어 있지 않습니다.** 패치는 차분(diff) 파일이며,
> **본인이 합법적으로 소유한 게임의 원본 `alldata.bin`** 에만 적용됩니다.

---

## 준비물

원본(무수정) `alldata.bin`이 필요하며 해시가 일치해야 합니다.

| 항목 | 값 |
|---|---|
| 파일 | `windata\alldata.bin` |
| 크기 | `853,831,680` bytes |
| SHA1 | `45a7bb1dc98e01b0e55c0038f1f9357048944a8a` |
| MD5 | `ffc1fd1b79a313802093c1ecc1cb7c3a` |

패치 적용 후 SHA1: `bec42de24b887c446e94d02d0a0555d02aec2ec2`

## 적용 방법

**방법 A — 동봉 스크립트 (Python)**

```bat
pip install pyxdelta
python apply_patch.py "C:\...\Castlevania Dominus Collection\windata\alldata.bin"
```

원본을 `alldata.bin.bak`으로 백업한 뒤 한글판으로 교체합니다.

**방법 B — Delta Patcher / xdelta3 (GUI·CLI)**

원본 `alldata.bin` + `DominusKorean_v1.xdelta` → 출력 파일을 `alldata.bin`으로 교체.

## 게임 내 언어 설정

- **창월의 십자가 / 빼앗긴 각인**: 게임 언어를 **일본어**로 설정 (일본어 트랙을 교체했기 때문)
- **오더 오브 에클레시아**: 언어 설정의 **한국어** 그대로

## 범위와 한계

- 창월/각인: 전 대사·아이템·메뉴 한글 (원 팬패치 기준). 그래픽(텍스처) 텍스트는 미포함.
  원 팬패치가 일본어로 남겨둔 극소수 구간은 그대로 유지
- 에클레시아: 대사는 공식 번역 유지, 고유명사만 한글화.
  HUD 약어(LV/EXP/ATK 등)와 영문 원제 BGM은 폰트 제약으로 영문 유지
- PC판 전용 폰트 파일 1종(형식 미해독)은 원본 유지 — 일부 소형 텍스트가
  일본어 글리프로 보이면 이슈로 제보 바랍니다

## 저장소 구성

```
DominusKorean_v1.xdelta   패치 본체
apply_patch.py            적용 스크립트 (해시 검증 포함)
docs/                     리버스 엔지니어링 문서
  MessageCodeMapping.md     메시지 인코딩(조밀 rank·폰트 회전) 해석
  KoreanPatchRebuild.md     기존 exe 패치의 결함 3종과 재구축 방법
  PIPELINE.md               대사 추출→수정→삽입 파이프라인 사용법
  WORKLOG.md                전체 작업 일지
tools/                    분석·빌드 도구 (연구/재현용, 경로는 작업 환경 기준)
  build_mapping.py          폰트 내장 코드로 문자표 추출
  build_korean_patch.py     패치 리빌더
  identify_hangul.py        한글 글리프 식별기 (템플릿 매칭+단조 DP)
  pipeline/                 대사 편집 파이프라인
tables/                   한글 글리프↔문자 식별표 (창월/각인)
```

## 기술 요약

- 메시지 텍스트는 SJIS 정렬 문자집합의 순번(dense rank) 토큰. 문자표는 폰트
  DAT 레코드에 내장된 코드 체인에서 추출 (docs/MessageCodeMapping.md)
- 기존 NDS용 패치 exe가 컬렉션에서 깨진 원인: 구버전 기준 절대주소(+0x3800),
  폰트 회전 배열 무시, 레코드 코드 필드 파괴 — 세 가지를 모두 보정해 재이식
- 에클레시아 한글 폰트는 KS X 1001 완성형 2350자 전체 수록이 확인되어
  자유로운 표기 개선이 가능했음

## 크레딧

- **창월의 십자가·빼앗긴 각인 한국어 번역**: 원 NDS 팬 한글패치 제작자
  (Dra01/Dra02KoreanV3 — 제작자 연락처를 알지 못해 사전 허락을 구하지 못했습니다.
  문제가 있다면 이슈로 알려주세요. 이 패치는 해당 번역을 컬렉션에서 다시 동작하게
  만든 재이식입니다)
- 원 게임: KONAMI / M2 (Castlevania Dominus Collection)
- 재이식·구조 해석·도구·번역 개선: snake7594 (with Claude)

본 패치는 비영리 팬 프로젝트이며, 원 게임의 구매를 대체하지 않습니다.
