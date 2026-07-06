# -*- coding: utf-8 -*-
"""빌드된 alldata.korean-rebuild.bin 검증: 메시지+폰트를 다시 읽어 렌더링."""
from pathlib import Path
from PIL import Image, ImageDraw
import struct, sys

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

QN = Path(r'C:\Users\Jay\Documents\Codex\2026-07-04\qn')
OUT = Path(r'C:\CHRONOS Releases\Castlevania Dominus Collection\windata\alldata.korean-rebuild.bin')
f = open(OUT, 'rb')

def rd(off, n):
    f.seek(off); return f.read(n)

CFG = {
    'd1': dict(res0=0x1E26117C, res_len=80079, big=(0x1D9AA560, 31642), sm=(0x1D9C1840, 12570), n=1291),
    'd2': dict(res0=0x208D197C, res_len=104695, big=(0x1F75E4C0, 35854), sm=(0x1F7788F0, 14190), n=1862),
}

def load_font(off, size, stride, charset):
    dat = rd(off, size)
    rank_of = {c: r for r, c in enumerate(charset)}
    pos = {}
    for ch in scan_chains(dat, stride):
        if len(ch) < 15:
            continue
        for o, c in ch:
            r = rank_of.get(c)
            if r is not None:
                pos[r] = o
    bm = {}
    for r, o in pos.items():
        if o + stride <= size:
            bm[r] = dat[o+2:o+stride]
    return bm

def glyph_img(bm24, w=16, rows=12):
    img = Image.new('1', (w, rows), 1)
    px = img.load()
    for r in range(rows):
        row = int.from_bytes(bm24[r*2:r*2+2], 'big')
        for x in range(w):
            if row & (0x8000 >> x):
                px[x, r] = 0
    return img

def glyph_img8(bm8):
    img = Image.new('1', (8, 8), 1)
    px = img.load()
    for r in range(8):
        for x in range(8):
            if bm8[r] & (0x80 >> x):
                px[x, r] = 0
    return img

for game, cfg in CFG.items():
    # 문자집합: 패치 후에도 코드 보존 → 체인 재스캔 가능해야 함
    dat = rd(*cfg['big'])
    chains = [c for c in scan_chains(dat, 26) if len(c) >= 15]
    charset = [x[1] for ch in chains for x in ch]
    assert all(a < b for a, b in zip(charset, charset[1:])), 'charset broken after patch!'
    print(game, 'post-patch charset intact:', len(charset))
    bigbm = load_font(cfg['big'][0], cfg['big'][1], 26, charset)
    smbm = load_font(cfg['sm'][0], cfg['sm'][1], 10, charset)

    res = rd(cfg['res0'], cfg['res_len'])
    cnt = struct.unpack_from('<I', res, 0)[0]
    assert cnt == cfg['n'], cnt
    offs = [struct.unpack_from('<I', res, 4+i*4)[0] for i in range(cnt)]
    ends = offs[1:] + [len(res)]

    def entry_tokens(i):
        seg = res[offs[i]:ends[i]]
        return [int.from_bytes(seg[j:j+2], 'little') for j in range(0, len(seg)-1, 2)]

    # 샘플 엔트리 렌더 (big font): 이름/아이템/대사 구간
    if game == 'd1':
        samples = [0, 1, 2, 3, 5, 30, 100, 200, 500, 800, 1191, 1200, 1290]
    else:
        samples = [0, 1, 2, 4, 50, 300, 700, 1400, 1500, 1600, 1861]
    strips = []
    for i in samples:
        toks = entry_tokens(i)
        glyphs = []
        for t in toks:
            if 0x8140 <= t <= 0x88FF:
                r = dense_rank(t)
                if r in bigbm:
                    glyphs.append(glyph_img(bigbm[r]))
            elif t == 0xF006:  # 개행 -> 공백으로
                glyphs.append(Image.new('1', (8, 12), 1))
            if len(glyphs) >= 34:
                break
        if glyphs:
            strip = Image.new('1', (sum(g.width for g in glyphs), 12), 1)
            x = 0
            for g in glyphs:
                strip.paste(g, (x, 0)); x += g.width
            strips.append((i, strip))
    S = 3
    H = sum(s.height*S+8 for _, s in strips)
    Wm = max(s.width*S for _, s in strips) + 60
    img = Image.new('RGB', (Wm, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    y = 0
    for i, s in strips:
        d.text((2, y+8), str(i), fill=(200, 0, 0))
        img.paste(s.resize((s.width*S, s.height*S)).convert('RGB'), (52, y))
        y += s.height*S + 8
    p = QN / f'work/claude_mapping/verify_{game}_big.png'
    img.save(p); print('saved', p)

    # small font 렌더: 첫 아이템/이름 몇 개
    strips = []
    for i in samples[:6]:
        toks = entry_tokens(i)
        glyphs = []
        for t in toks:
            if 0x8140 <= t <= 0x88FF:
                r = dense_rank(t)
                if r in smbm:
                    glyphs.append(glyph_img8(smbm[r]))
            if len(glyphs) >= 40:
                break
        if glyphs:
            strip = Image.new('1', (8*len(glyphs), 8), 1)
            for k, g in enumerate(glyphs):
                strip.paste(g, (k*8, 0))
            strips.append((i, strip))
    S = 4
    H = sum(s.height*S+8 for _, s in strips)
    Wm = max(s.width*S for _, s in strips) + 60
    img = Image.new('RGB', (Wm, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    y = 0
    for i, s in strips:
        d.text((2, y+6), str(i), fill=(200, 0, 0))
        img.paste(s.resize((s.width*S, s.height*S)).convert('RGB'), (52, y))
        y += s.height*S + 8
    p = QN / f'work/claude_mapping/verify_{game}_small.png'
    img.save(p); print('saved', p)

f.close()
print('verification renders complete')
