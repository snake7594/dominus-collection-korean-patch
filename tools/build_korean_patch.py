# -*- coding: utf-8 -*-
"""
Castlevania Dominus Collection (Dra01/Dra02) 한글패치 리빌더.

원리 (MessageCodeMapping.md 참조):
- 메시지 토큰 = 문자집합의 dense rank (rank_to_code / dense_rank).
- 폰트 DAT = [SJIS코드 2B][비트맵] 레코드 배열. rank r 슬롯의 위치는
  DAT 안의 오름차순 코드 체인을 스캔해 얻는다 (플랫폼 변형별로 구조 다름).
- 기존 패치 exe 리소스: BigFont/SmallFont 레코드 r == rank r 의 한글 글리프.
  메시지(한국어 번역)는 이미 dense rank 토큰으로 인코딩돼 있음.
- exe가 깨졌던 이유: (1) 폰트를 파일 선두에 통째로 덮어 회전(rotation) 무시,
  (2) 메시지 오프셋이 구버전 message.psb 기준(+0x3800), (3) 레코드의 내장 코드 파괴.
- 이 빌더는 원본 alldata에서: 메시지는 올바른 리소스 위치에, 폰트는 rank별
  정확한 비트맵 위치에(코드 보존) 기록한다. wrap 슬롯(비트맵이 파일 경계에
  걸린 레코드)은 미사용 rank로 토큰을 리매핑해 회피한다.
"""
from pathlib import Path
import struct, pickle, io, shutil, hashlib, sys

QN = Path(r'C:\Users\Jay\Documents\Codex\2026-07-04\qn')
WINDATA = Path(r'C:\CHRONOS Releases\Castlevania Dominus Collection\windata')
SRC = WINDATA / 'alldata-원본.bin'
OUT = WINDATA / 'alldata.korean-rebuild.bin'
P1 = QN / 'work/patchers_extract/Dra01KoreanV3-0'
P2 = QN / 'work/patchers_extract/Dra02KoreanV3-0'

SHIFT = 0x3800  # 구버전 message.psb 내부 오프셋 차이

# ---------- 공통 ----------

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
    tr = 0x40 + r + (1 if r >= 0x3F else 0)
    return (lead << 8) | tr


class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError('blocked')

def sload(p):
    return SafeUnpickler(io.BytesIO(Path(p).read_bytes())).load()


class Writer:
    """기록 범위를 추적하고 허용 영역 밖 기록을 차단한다."""
    def __init__(self, f, allowed):
        self.f = f
        self.allowed = allowed  # list of (start, end, tag)
        self.log = []

    def write(self, off, data):
        ok = any(s <= off and off + len(data) <= e for s, e, _ in self.allowed)
        assert ok, f'write outside allowed region: 0x{off:X} +{len(data)}'
        self.f.seek(off)
        self.f.write(data)
        self.log.append((off, len(data)))


def rank_positions(dat, stride, charset):
    """DAT에서 {rank: 코드 오프셋} 부분 매핑을 만든다.

    charset: rank 순 SJIS 코드 리스트(NX big에서 확정). 일부 변형(PS5 small)은
    저영역에 코드가 없어 체인이 부분적으로만 나오므로, 찾은 코드만 rank에 대응.
    """
    rank_of = {c: r for r, c in enumerate(charset)}
    chains = [c for c in scan_chains(dat, stride) if len(c) >= 15]
    pos = {}
    for ch in chains:
        for o, c in ch:
            r = rank_of.get(c)
            if r is not None:
                assert r not in pos, f'dup rank {r}'
                pos[r] = o
    wrap = {r for r, o in pos.items() if o + stride > len(dat)}
    return pos, wrap

# ---------- 준비 ----------

print('== loading resources ==')
d1_big = (P1/'resources_BigFont').read_bytes()      # 1090 * 26
d1_small = (P1/'resources_SmallFont').read_bytes()  # 829 * 10 (rank 234..1062)
d1_orders = (P1/'resources_OrdersData').read_bytes()
d1_sent = bytearray((P1/'resources_SentencesData').read_bytes())
d2_big = (P2/'resources_BigFont').read_bytes()      # 1330 * 26
d2_small = (P2/'resources_SmallFont').read_bytes()  # 1330 * 10
link = sload(P2/'resources_LinkMap')
kor = sload(P2/'resources_Korean')
rom = sload(P2/'resources_RomDataMap')
imginfo = sload(P2/'resources_ImageInfoMap')

# Dra01 small 레코드의 내장 코드 == rank_to_code(234+k) 확인
for k in range(0, 829, 97):
    le = int.from_bytes(d1_small[k*10:k*10+2], 'little')
    assert le == rank_to_code(234+k), f'd1 small rec {k}: {le:04X}'
# Dra02는 big/small 모두 [BE NDS-SJIS 코드][비트맵] — 두 리소스의 코드 열이
# 완전히 일치하면 레코드 k == rank k 정렬이 서로 일관된 것
d2_big_codes = [int.from_bytes(d2_big[k*26:k*26+2], 'big') for k in range(1330)]
d2_sm_codes = [int.from_bytes(d2_small[k*10:k*10+2], 'big') for k in range(1330)]
assert d2_big_codes == d2_sm_codes, 'd2 big/small code sequence mismatch'
print('patch smallfont rank alignment OK (d1 LE codes, d2 big==small)')

# 원본 메시지 리소스
m1 = (QN/'work/original_psb_raw/dra01_message/orig_1e261000_dra01_message/0.bin').read_bytes()
m2 = (QN/'work/original_psb_raw/dra02_message/orig_208d1800_dra02_message/0.bin').read_bytes()
D1_RES0 = 0x1E26117C
D2_RES0 = 0x208D197C

# ---------- Dra01 메시지 ----------
print('== dra01 message ==')
offs1 = struct.unpack_from('<1291I', d1_orders, 0)
assert offs1[0] == 0x1430
assert all(o % 2 == 0 for o in offs1)
# 토큰 리매핑: rank551(0x83F0, big wrap) -> rank1083(0x86D0)
D1_REMAP = {0x83F0: 0x86D0}
n_remap = 0
for j in range(0, len(d1_sent)-1, 2):
    t = int.from_bytes(d1_sent[j:j+2], 'little')
    if t in D1_REMAP:
        d1_sent[j:j+2] = D1_REMAP[t].to_bytes(2, 'little')
        n_remap += 1
print(f'dra01 tokens remapped: {n_remap}')
# 검증: 최대 rank
mx = max(dense_rank(int.from_bytes(d1_sent[j:j+2],'little'))
         for j in range(0,len(d1_sent)-1,2)
         if 0x8140 <= int.from_bytes(d1_sent[j:j+2],'little') <= 0x87FF)
assert mx <= 1083, mx

# ---------- Dra02 메시지 (가상 적용) ----------
print('== dra02 message ==')
cnt2 = struct.unpack_from('<I', m2, 0)[0]
offs2 = [struct.unpack_from('<I', m2, 4+i*4)[0] for i in range(cnt2)]
ends2 = offs2[1:] + [len(m2)]
starts2 = {offs2[i]+2: i for i in range(cnt2)}

res2 = bytearray(m2)
# 1차: 리매핑 없이 적용해 '남는 원본 토큰' 집합 계산
written_positions = []
for (pc_s, pc_e), romkey in link.items():
    rs = pc_s - SHIFT - D2_RES0
    assert rs in starts2, hex(pc_s)
    i = starts2[rs]
    body_end = ends2[i] - 2
    sent = kor[romkey]
    assert rs + 2*len(sent) <= body_end + 2, f'entry {i} overflow'
    p = rs
    for key in sent:
        code = rom[key]
        if code != '0000':
            res2[p:p+2] = bytes.fromhex(code)
            written_positions.append(p)
        p += 2
kept_tokens = set()
for i in range(cnt2):
    seg = res2[offs2[i]:ends2[i]]
    for j in range(0, len(seg)-1, 2):
        kept_tokens.add(int.from_bytes(seg[j:j+2], 'little'))
wp = set(written_positions)
orig_kept = set()
for i in range(cnt2):
    for j in range(offs2[i], ends2[i]-1, 2):
        if j not in wp:
            orig_kept.add(int.from_bytes(res2[j:j+2], 'little'))
# 리매핑 대상: big wrap rank551(0x83F0), small wrap rank14(0x814E)
# 대상 rank: 1157..1338 중 최종 데이터에 등장하지 않는 코드
free = [r for r in range(1157, 1339)
        if rank_to_code(r) not in kept_tokens]
assert len(free) >= 2, free
D2_REMAP = {0x83F0: rank_to_code(free[0]), 0x814E: rank_to_code(free[1])}
print(f'dra02 remap: 83F0->{D2_REMAP[0x83F0]:04X} (rank {free[0]}), '
      f'814E->{D2_REMAP[0x814E]:04X} (rank {free[1]})')
# 2차: 리매핑 반영 재적용
res2 = bytearray(m2)
n_remap2 = 0
for (pc_s, pc_e), romkey in link.items():
    rs = pc_s - SHIFT - D2_RES0
    p = rs
    for key in kor[romkey]:
        code = rom[key]
        if code != '0000':
            t = int.from_bytes(bytes.fromhex(code), 'little')
            if t in D2_REMAP:
                t = D2_REMAP[t]; n_remap2 += 1
            res2[p:p+2] = t.to_bytes(2, 'little')
        p += 2
print(f'dra02 tokens written with remap: {n_remap2} remapped')
d2_rank_src = {free[0]: 551, free[1]: 14}   # 새 rank <- 원 rank (폰트 주입용)

# ---------- 출력 파일 생성 ----------
print('== copying base file ==')
if not OUT.exists() or OUT.stat().st_size != SRC.stat().st_size:
    shutil.copyfile(SRC, OUT)
f = open(OUT, 'r+b')

FONTS = {
    # name: (offset, size, stride)
    'd1bigNX':  (0x1D9AA560, 31642, 26), 'd1bigPS5': (0x1D9B2100, 31642, 26),
    'd1bigWIN': (0x1D9B9CA0, 31642, 26),
    'd1smNX':   (0x1D9C1840, 12570, 10), 'd1smPS5':  (0x1D9C4960, 12570, 10),
    'd2bigNX':  (0x1F75E4C0, 35854, 26), 'd2bigPS5': (0x1F7670D0, 35854, 26),
    'd2bigWIN': (0x1F76FCE0, 35854, 26),
    'd2smNX':   (0x1F7788F0, 14190, 10), 'd2smPS5':  (0x1F77C060, 14190, 10),
}
allowed = [(D1_RES0+4, D1_RES0+len(m1), 'd1msg'), (D2_RES0+4, D2_RES0+len(m2), 'd2msg')]
for name, (off, size, _) in FONTS.items():
    allowed.append((off, off+size, name))
for (s, e), tag in imginfo.items():
    allowed.append((s, e, str(tag)))
w = Writer(f, allowed)

# ---------- 메시지 기록 ----------
w.write(D1_RES0 + 4, d1_orders)                       # 오프셋 테이블
text_area = len(m1) - 0x1430                          # 74911
w.write(D1_RES0 + 0x1430, bytes(text_area))           # clear
w.write(D1_RES0 + 0x1430, bytes(d1_sent))             # 본문 74408
print(f'dra01 message written (table 5164 + text {len(d1_sent)}/{text_area})')

w.write(D2_RES0 + 4, bytes(res2[4:]))                 # count 보존, 테이블+본문
print(f'dra02 message written ({len(res2)-4} bytes)')

# ---------- 폰트 주입 ----------

def read_font(off, size):
    f.seek(off); return f.read(size)

CHARSETS = {}

def charset_for(game):
    if game not in CHARSETS:
        base = FONTS[f'{game}bigNX']
        dat = read_font(base[0], base[1])
        chains = [c for c in scan_chains(dat, 26) if len(c) >= 15]
        codes = [x[1] for ch in chains for x in ch]
        assert all(a < b for a, b in zip(codes, codes[1:]))
        assert len(codes) == (1177 if game == 'd1' else 1339)
        CHARSETS[game] = codes
    return CHARSETS[game]

def inject(name, ranks_bitmaps):
    """ranks_bitmaps: {rank: bitmap(bytes)} — 찾을 수 있는 슬롯에만 기록."""
    off, size, stride = FONTS[name]
    dat = read_font(off, size)
    pos, wraps = rank_positions(dat, stride, charset_for(name[:2]))
    bmlen = stride - 2
    n = skipped = 0
    for r, bm in ranks_bitmaps.items():
        if r in wraps or r not in pos:
            skipped += 1
            continue
        assert len(bm) == bmlen
        w.write(off + pos[r] + 2, bm)
        n += 1
    print(f'{name}: {n} glyphs injected, {skipped} skipped (wrap/absent)')

def big_rec(res, r):
    return res[r*26+2:r*26+26]

def small_rec(res, k):
    return res[k*10+2:k*10+10]

# --- Dra01 big: 패치 레코드 r == rank r (0..1089), 551은 1083으로 이동
d1_big_map = {r: big_rec(d1_big, r) for r in range(1090) if r != 551}
d1_big_map[1083] = big_rec(d1_big, 551)
for name in ('d1bigNX', 'd1bigPS5'):
    inject(name, d1_big_map)

# --- Dra01 small: 패치 레코드 k == rank 234+k, 551->1083
d1_sm_map = {234+k: small_rec(d1_small, k) for k in range(829) if 234+k != 551}
d1_sm_map[1083] = small_rec(d1_small, 551-234)
for name in ('d1smNX', 'd1smPS5'):
    inject(name, d1_sm_map)

# --- Dra01 WIN big: 26B 한자 섹션(rank 552..1176) + 8x8 전체 섹션
off, size, _ = FONTS['d1bigWIN']
datW = read_font(off, size)
ch26 = [c for c in scan_chains(datW, 26) if len(c) >= 15]
assert len(ch26) == 1 and ch26[0][0][1] == 0x8DDE
n = 0
for r, bm in d1_big_map.items():
    if r < 552:
        continue
    o = ch26[0][0][0] + 26*(r-552)
    w.write(off + o + 2, bm); n += 1
ch10 = [c for c in scan_chains(datW, 10) if len(c) >= 176]
full10 = [c for c in ch10 if len(c) == 1177]
assert full10, [len(c) for c in ch10]
base10 = full10[0][0][0]
n2 = 0
for r, bm in d1_sm_map.items():
    o = base10 + 10*r
    if o + 10 <= size:
        w.write(off + o + 2, bm); n2 += 1
print(f'd1bigWIN: {n} kanji(12px) + {n2} glyphs(8px) injected')

# --- Dra02 big: 패치 레코드 r == rank r (0..1329), remap 소스 스킵+타깃 기록
skip_src = set(d2_rank_src.values())          # {551, 14}
d2_big_map = {r: big_rec(d2_big, r) for r in range(1330) if r not in skip_src}
for newr, srcr in d2_rank_src.items():
    d2_big_map[newr] = big_rec(d2_big, srcr)
for name in ('d2bigNX', 'd2bigPS5'):
    inject(name, d2_big_map)

# --- Dra02 small: 레코드 r == rank r, ranks 0..14 스킵(기호, 원본 유지)
d2_sm_map = {r: small_rec(d2_small, r) for r in range(15, 1330) if r not in skip_src}
for newr, srcr in d2_rank_src.items():
    d2_sm_map[newr] = small_rec(d2_small, srcr)
for name in ('d2smNX', 'd2smPS5'):
    inject(name, d2_sm_map)

# --- Dra02 WIN big: 26B 한자 섹션 + 8x8 전체 섹션
off, size, _ = FONTS['d2bigWIN']
datW = read_font(off, size)
ch26 = [c for c in scan_chains(datW, 26) if len(c) >= 15]
assert len(ch26) == 1 and ch26[0][0][1] == 0x8D51
n = 0
for r, bm in d2_big_map.items():
    if r < 552:
        continue
    o = ch26[0][0][0] + 26*(r-552)
    w.write(off + o + 2, bm); n += 1
ch10 = [c for c in scan_chains(datW, 10) if len(c) == 1339]
assert ch10
base10 = ch10[0][0][0]
n2 = 0
for r, bm in d2_sm_map.items():
    o = base10 + 10*r
    if o + 10 <= size:
        w.write(off + o + 2, bm); n2 += 1
print(f'd2bigWIN: {n} kanji(12px) + {n2} glyphs(8px) injected')

# ---------- Dra02 이미지 ----------
for (s, e), tag in imginfo.items():
    payload = (P2/f'resources_{tag}').read_bytes()
    assert len(payload) == e - s, (tag, len(payload), e-s)
    w.write(s, payload)
print(f'dra02 images: {len(imginfo)} payloads written')

f.close()
h = hashlib.sha256()
with open(OUT, 'rb') as rf:
    for chunk in iter(lambda: rf.read(1 << 22), b''):
        h.update(chunk)
print('DONE. writes:', len(w.log), 'sha256:', h.hexdigest())
print('output:', OUT)
