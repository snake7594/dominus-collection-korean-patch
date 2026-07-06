# -*- coding: utf-8 -*-
"""Dominus Collection 대사 편집 파이프라인 공용 모듈.

게임별 텍스트 인코딩:
- dra01/dra02: 2바이트 LE 토큰 = 문자집합 dense rank (한글패치로 한글 글리프 주입됨)
- dra03  ko  : 2바이트 LE 토큰 = raw EUC-KR(cp949) 코드 (공식 한국어)
- dra03  ja  : dense rank (선형 폰트, 회전 없음)
제어 토큰: 0xF0xx(<F006>=개행 등), 0x00xx(파라미터) -> 태그 <XXXX>로 왕복 보존.
알 수 없는 토큰 -> <t:XXXX>.
"""
from pathlib import Path
import csv, struct

QN = Path(r'C:\Users\Jay\Documents\Codex\2026-07-04\qn')
WINDATA = Path(r'C:\CHRONOS Releases\Castlevania Dominus Collection\windata')
ALLDATA = WINDATA / 'alldata.bin'
TEXTDIR = QN / 'pipeline' / 'text'

GAMES = {
    'dra01': dict(
        res0=0x1E26117C, res_len=80079, count=1291,
        table_fixed=True,          # 텍스트 영역만 가변 (테이블 크기 고정)
        big=dict(NX=0x1D9AA560, PS5=0x1D9B2100, WIN=0x1D9B9CA0), big_size=31642,
        small=dict(NX=0x1D9C1840, PS5=0x1D9C4960), small_size=12570,
        charset_n=1177,
        free_ranks=list(range(1084, 1177)),   # 새 글자용 (원본 한자 슬롯, 미사용 확인 후)
        hangul_tsv='dra01_rank_to_hangul.tsv',
        code_tsv='outputs/dra01_dialogue/dra01_code_to_char_full.tsv',
        ref_json='outputs/dra01_dialogue/dra01_jp_full_text.json',
    ),
    'dra02': dict(
        res0=0x208D197C, res_len=104695, count=1862,
        table_fixed=True,
        big=dict(NX=0x1F75E4C0, PS5=0x1F7670D0, WIN=0x1F76FCE0), big_size=35854,
        small=dict(NX=0x1F7788F0, PS5=0x1F77C060), small_size=14190,
        charset_n=1339,
        free_ranks=list(range(1159, 1339)),
        hangul_tsv='dra02_rank_to_hangul.tsv',
        code_tsv='outputs/dra02_dialogue/dra02_code_to_char_full.tsv',
        ref_json='outputs/dra02_dialogue/dra02_jp_full_text.json',
    ),
    'dra03': dict(
        res_ja=0x230A597E, res_ja_len=143723,
        res_ko=0x230C8AE9, res_ko_len=157211, count=1927,
        big=dict(NX=0x2237AD40, PS5=0x2237AD40+38880, WIN=0x2237AD40+2*38880),
        big_size=38870,
        kor12=dict(NX=0x2233BFD0, PS5=0x2233BFD0+80528, WIN=0x2233BFD0+2*80528),
    ),
}


def valid_sjis(c):
    lead, tr = c >> 8, c & 0xFF
    if not (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xEA):
        return False
    if not (0x40 <= tr <= 0xFC) or tr == 0x7F:
        return False
    try:
        c.to_bytes(2, 'big').decode('cp932'); return True
    except Exception:
        return False


def scan_chains(dat, stride, min_len=15):
    chains = []
    N = len(dat)
    for phase in range(stride):
        o = phase; cur = []; prev = -1
        while o + 2 <= N:
            c = int.from_bytes(dat[o:o+2], 'big')
            if valid_sjis(c) and c > prev:
                cur.append((o, c)); prev = c
            else:
                if len(cur) >= min_len:
                    chains.append(cur)
                cur = [(o, c)] if valid_sjis(c) else []
                prev = c if valid_sjis(c) else -1
            o += stride
        if len(cur) >= min_len:
            chains.append(cur)
    chains.sort(key=lambda ch: ch[0][1])
    return chains


def dense_rank(code):
    lead, tr = code >> 8, code & 0xFF
    return (lead - 0x81) * 188 + (tr - 0x40) - (1 if tr > 0x7F else 0)


def rank_to_code(rank):
    lead = 0x81 + rank // 188
    r = rank % 188
    return (lead << 8) | (0x40 + r + (1 if r >= 0x3F else 0))


def read_at(f, off, n):
    f.seek(off); return f.read(n)


def parse_resource(res, term=0xF00A):
    """엔트리 = offs[i]부터 종결자(F00A)까지.

    주의: 기존 한글패치의 dra01 테이블은 비단조(문자열 공유)라서
    '다음 오프셋까지'로 자르면 안 된다. 종결자 기준이 안전.
    """
    cnt = struct.unpack_from('<I', res, 0)[0]
    offs = [struct.unpack_from('<I', res, 4 + i*4)[0] for i in range(cnt)]
    entries = []
    for i in range(cnt):
        toks = []
        o = offs[i]
        while o + 2 <= len(res):
            t = int.from_bytes(res[o:o+2], 'little')
            toks.append(t)
            o += 2
            if t == term:
                break
        entries.append(toks)
    return entries


def build_decode_tables(game):
    """dra01/02: rank -> 문자 (한글표 + 원본 문자표 병합), 역방향 표."""
    cfg = GAMES[game]
    rank2ch = {}
    for row in list(csv.reader(open(QN / 'work/claude_mapping' / cfg['hangul_tsv'],
                                    encoding='utf-8'), delimiter='\t'))[1:]:
        rank2ch[int(row[0])] = row[1]
    hangul_ranks = set(rank2ch)
    for row in list(csv.reader(open(QN / cfg['code_tsv'], encoding='utf-8'),
                               delimiter='\t'))[1:]:
        r = dense_rank(int(row[0], 16))
        if r not in rank2ch:          # 한글이 주입 안 된 슬롯 = 원본 문자
            rank2ch[r] = row[2]
    ch2rank = {}
    for r, ch in sorted(rank2ch.items()):
        # 한글 우선, 그 외 첫 등장 우선
        if ch not in ch2rank or (r in hangul_ranks):
            ch2rank.setdefault(ch, r)
    return rank2ch, ch2rank, hangul_ranks


def decode_entry_ranked(tokens, rank2ch, lo=0x8140, hi=0x88FF):
    out = []
    for t in tokens:
        if lo <= t <= hi:
            r = dense_rank(t)
            if r in rank2ch:
                out.append(rank2ch[r]); continue
            out.append(f'<t:{t:04X}>'); continue
        out.append(f'<{t:04X}>')
    return ''.join(out)


def decode_entry_euc(tokens):
    out = []
    for t in tokens:
        if 0xA1A1 <= t <= 0xFDFE and (t & 0xFF) >= 0xA1:
            try:
                out.append(t.to_bytes(2, 'big').decode('cp949')); continue
            except Exception:
                pass
        out.append(f'<{t:04X}>')
    return ''.join(out)


import re
TAG = re.compile(r'<(t:)?([0-9A-Fa-f]{4})>')

def encode_text(text, ch2rank=None, new_alloc=None):
    """태그+문자 -> 토큰 리스트. ch2rank=None이면 EUC-KR 모드(dra03 ko).
    new_alloc: 미등록 한글 처리 콜백 char->rank (없으면 예외)."""
    toks = []
    i = 0
    while i < len(text):
        m = TAG.match(text, i)
        if m:
            toks.append(int(m.group(2), 16))
            i = m.end(); continue
        ch = text[i]; i += 1
        if ch2rank is None:                      # dra03 ko: raw EUC-KR
            try:
                b = ch.encode('cp949')
            except Exception:
                raise ValueError(f'cp949 인코딩 불가 문자: {ch!r}')
            if len(b) != 2:
                # 반각 문자는 전각으로 자동 변환 시도
                full = chr(ord(ch) + 0xFEE0) if 0x21 <= ord(ch) <= 0x7E else ('　' if ch == ' ' else None)
                if full:
                    b = full.encode('cp949')
                else:
                    raise ValueError(f'2바이트 문자 아님: {ch!r}')
            toks.append(int.from_bytes(b, 'big'))
        else:                                     # dra01/02: rank 토큰
            if ch == ' ':
                ch = '　'
            if ch in ch2rank:
                toks.append(rank_to_code(ch2rank[ch]))
            elif '가' <= ch <= '힣' and new_alloc:
                toks.append(rank_to_code(new_alloc(ch)))
            else:
                raise ValueError(f'폰트에 없는 문자: {ch!r} (신규 할당 불가)')
    return toks


def rebuild_resource(entries_tokens, total_budget, count):
    """entries -> count+table+text 바이트. 동일 문자열은 공유(dedup).

    예산 초과 시 예외.
    """
    assert len(entries_tokens) == count
    table_end = 4 + count * 4
    blob = bytearray()
    offs = []
    seen = {}
    for toks in entries_tokens:
        key = tuple(toks)
        if key in seen:
            offs.append(seen[key])
            continue
        o = table_end + len(blob)
        seen[key] = o
        offs.append(o)
        for t in toks:
            blob += t.to_bytes(2, 'little')
    total = table_end + len(blob)
    if total > total_budget:
        raise ValueError(f'크기 초과: {total} > {total_budget} ({total-total_budget}바이트 줄여야 함)')
    out = bytearray(struct.pack('<I', count))
    for o in offs:
        out += struct.pack('<I', o)
    out += blob
    out += bytes(total_budget - total)   # 잔여 0 채움
    return bytes(out), total
