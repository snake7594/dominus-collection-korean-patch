# -*- coding: utf-8 -*-
"""
Dra01/Dra02 게임 메시지 코드 -> 문자 매핑 테이블 생성.

핵심 발견:
- 폰트 LD937714*.DAT 각 레코드에는 해당 글리프의 표준 Shift-JIS(cp932) 코드가 내장되어 있다.
- 메시지 코드(0x8140~)는 SJIS와 같은 lead/trail 구조(trail 0x40-0xFC, 0x7F 제외, 188/행)의
  '조밀(dense) 인덱스'이며, 폰트 레코드 배열과는 회전(rotation) 오프셋으로 대응한다.
- 파일 레이아웃(레코드 26바이트 슬라이싱 기준):
    glyph 1..A     : 코드가 offset 26n-10 에 위치 (한자 후반부, SJIS 오름차순)
    glyph R..last  : 코드가 offset 26n-4  에 위치 (0x8140부터 기호/가나/한자 전반부)
    glyph 0        : 코드가 파일 끝-4 위치 (wrap)
    그 사이 40개(코드 없음) = 특수 그래픽 글리프(메시지 코드 도달 불가)
- 검증: 코드 체인은 각 영역에서 SJIS 오름차순이어야 하며,
  게임코드 dense rank == 코드 체인상의 rank 로 1:1 대응.
"""
from pathlib import Path
import struct, json, csv

ROOT = Path(r'C:\Users\Jay\Documents\Codex\2026-07-04\qn')
OUT = ROOT / 'outputs'


def valid_sjis(c):
    lead, tr = c >> 8, c & 0xFF
    if not (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xEA):
        return False
    if not (0x40 <= tr <= 0xFC) or tr == 0x7F:
        return False
    try:
        c.to_bytes(2, 'big').decode('cp932')
        return True
    except Exception:
        return False


def scan_chains(dat, stride=26, min_len=20):
    """모든 위상에서 오름차순 SJIS 코드 체인을 찾는다."""
    chains = []
    N = len(dat)
    for phase in range(stride):
        o = phase
        cur = []
        prev = -1
        while o + 2 <= N:
            c = int.from_bytes(dat[o:o + 2], 'big')
            if valid_sjis(c) and c > prev:
                cur.append((o, c))
                prev = c
            else:
                if len(cur) >= min_len:
                    chains.append(cur)
                cur = [(o, c)] if valid_sjis(c) else []
                prev = c if valid_sjis(c) else -1
            o += stride
        if len(cur) >= min_len:
            chains.append(cur)
    return chains


def dense_rank(code):
    """게임 메시지 코드 -> dense rank (0x8140 = 0)."""
    lead, tr = code >> 8, code & 0xFF
    return (lead - 0x81) * 188 + (tr - 0x40) - (1 if tr > 0x7F else 0)


def rank_to_code(rank):
    lead = 0x81 + rank // 188
    r = rank % 188
    tr = 0x40 + r + (1 if r >= 0x3F else 0)  # 0x7F 건너뜀
    return (lead << 8) | tr


def build_game(game, dat_path, msg_raw_path, count_expected=None):
    dat = dat_path.read_bytes()
    nrec = len(dat) // 26
    chains = scan_chains(dat)
    chains.sort(key=lambda ch: ch[0][1])  # 시작 코드 기준 정렬
    assert len(chains) == 2, f'chain count = {len(chains)}'
    low, high = chains  # low: 0x8140.., high: 한자 후반부
    # 코드 시퀀스 연결: low(기호/가나/한자전반) 다음 high(한자후반). 파일 끝 wrap 코드가 low의 마지막.
    codes = [c for _, c in low] + [c for _, c in high]
    # 전체 오름차순 검증
    assert all(a < b for a, b in zip(codes, codes[1:])), 'codes not strictly ascending'
    print(f'[{game}] records={nrec}, chain low {len(low)} ({low[0][1]:04X}..{low[-1][1]:04X}), '
          f'high {len(high)} ({high[0][1]:04X}..{high[-1][1]:04X}), total {len(codes)}')

    # 게임코드 -> 문자
    mapping = {}
    for rank, sjis in enumerate(codes):
        gcode = rank_to_code(rank)
        ch = sjis.to_bytes(2, 'big').decode('cp932')
        mapping[gcode] = (sjis, ch)

    # 메시지에서 실제 쓰인 glyph 코드가 전부 매핑에 있는지 확인
    b = msg_raw_path.read_bytes()
    cnt = struct.unpack_from('<I', b, 0)[0]
    if count_expected:
        assert cnt == count_expected, cnt
    offs = [struct.unpack_from('<I', b, 4 + i * 4)[0] for i in range(cnt)]
    used = set()
    entries_codes = []
    for i in range(cnt):
        end = offs[i + 1] if i + 1 < cnt else len(b)
        seg = b[offs[i]:end]
        cs = [int.from_bytes(seg[j:j + 2], 'little') for j in range(0, len(seg) - 1, 2)]
        entries_codes.append(cs)
        for c in cs:
            if 0x8100 <= c <= 0x87FF or (0x8800 <= c <= 0x9FFF):
                used.add(c)
    missing = sorted(c for c in used if c not in mapping)
    print(f'[{game}] messages={cnt}, used glyph codes={len(used)}, missing from mapping={len(missing)}')
    if missing:
        print('  missing:', [f'{c:04X}' for c in missing[:20]])
    return mapping, entries_codes, cnt


def decode_entry(cs, mapping):
    parts = []
    for c in cs:
        if c in mapping:
            parts.append(mapping[c][1])
        elif c == 0xF00A:
            parts.append('')  # 종결자
        elif (c >> 8) == 0xF0:
            parts.append(f'<{c:04X}>')  # 제어 코드
        elif c < 0x100:
            parts.append(f'<{c:04X}>')  # 파라미터/제어
        else:
            parts.append(f'<?{c:04X}>')
    return ''.join(parts)


def write_outputs(game, mapping, entries_codes, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    # 1) 매핑 테이블
    with open(outdir / f'{game}_code_to_char_full.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['game_code', 'sjis_code', 'char'])
        for g in sorted(mapping):
            s, ch = mapping[g]
            w.writerow([f'{g:04X}', f'{s:04X}', ch])
    # 2) 전체 원문 TSV/JSON/미리보기
    rows = []
    for i, cs in enumerate(entries_codes):
        # 앞쪽 prefix(0x0000 등 제어), 본문, 종결자 분리하지 않고 전부 태그 포함 디코딩
        text = decode_entry(cs, mapping)
        rows.append({'index': i, 'codes': [f'{c:04X}' for c in cs], 'text': text})
    with open(outdir / f'{game}_jp_full_text.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['index', 'text'])
        for r in rows:
            w.writerow([r['index'], r['text'].replace('\n', '\\n')])
    with open(outdir / f'{game}_jp_full_text.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f'[{game}] wrote outputs to {outdir}')
    return rows


if __name__ == '__main__':
    # ---- Dra01 ----
    m1, e1, _ = build_game(
        'dra01',
        ROOT / 'work/font_extract/orig/dra01/LD937714NX.DAT',
        ROOT / 'work/original_psb_raw/dra01_message/orig_1e261000_dra01_message/0.bin',
        1291)
    # seed 검증
    seeds = [(int(r[0], 16), r[1]) for r in list(csv.reader(
        open(ROOT / 'outputs/dra01_dialogue/dra01_jp_mapping_seed.tsv', encoding='utf-8-sig'),
        delimiter='\t'))[1:]]
    ok = bad = 0
    for code, ch in seeds:
        got = m1.get(code, (0, None))[1]
        if got == ch:
            ok += 1
        else:
            bad += 1
            print(f'  SEED MISMATCH {code:04X}: expected {ch!r} got {got!r}')
    print(f'[dra01] seed check: {ok} ok, {bad} mismatch / {len(seeds)}')
    rows1 = write_outputs('dra01', m1, e1, OUT / 'dra01_dialogue')
    for r in rows1[:8]:
        print(' ', r['index'], r['text'][:60])

    # ---- Dra02 ----
    m2, e2, _ = build_game(
        'dra02',
        ROOT / 'work/font_extract/orig/dra02/LD937714NX.DAT',
        ROOT / 'work/original_psb_raw/dra02_message/orig_208d1800_dra02_message/0.bin',
        1862)
    rows2 = write_outputs('dra02', m2, e2, OUT / 'dra02_dialogue')
    for r in rows2[:8]:
        print(' ', r['index'], r['text'][:60])
