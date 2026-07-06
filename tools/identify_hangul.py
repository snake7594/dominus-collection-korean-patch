# -*- coding: utf-8 -*-
"""Dra01/Dra02 패치 폰트의 한글 글리프 -> 음절 식별.

방법: 굴림/굴림체 11~13px 템플릿과 픽셀 매칭 + 'rank 순 == KS(가나다) 순'
단조성 DP + 앵커(육안 확정 글자) 고정.
출력: work/claude_mapping/{game}_rank_to_hangul.tsv + 검수용 시트 PNG.
"""
from pathlib import Path
from PIL import Image, ImageFont, ImageDraw
import numpy as np
import struct, json

QN = Path(r'C:\Users\Jay\Documents\Codex\2026-07-04\qn')
OUTD = QN / 'work/claude_mapping'

KS_SYL = []
for lead in range(0xB0, 0xC9):
    for tr in range(0xA1, 0xFF):
        KS_SYL.append(bytes([lead, tr]).decode('cp949'))
KS_IDX = {c: i for i, c in enumerate(KS_SYL)}

W, H = 16, 12

def glyph_arr(bm24):
    a = np.zeros((H, W), dtype=bool)
    for r in range(H):
        row = int.from_bytes(bm24[r*2:r*2+2], 'big')
        for x in range(W):
            if row & (0x8000 >> x):
                a[r, x] = True
    return a

def render_templates():
    """각 음절을 (폰트변형 x 위치시프트)로 렌더한 템플릿 스택."""
    variants = []
    for idx in (0, 1):           # 굴림, 굴림체
        for size in (11, 12, 13):
            variants.append(ImageFont.truetype(r'C:\Windows\Fonts\gulim.ttc', size, index=idx))
    shifts = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, -1), (1, -1), (2, 1)]
    temps = []      # (n_var, 2350, H*W)
    for f in variants:
        for dx, dy in shifts:
            img = Image.new('L', (W * 64, H), 255)
            d = ImageDraw.Draw(img)
            # 한 줄에 64자씩 찍어 렌더 횟수 절약
            arrs = np.zeros((2350, H, W), dtype=bool)
            for base in range(0, 2350, 64):
                img.paste(255, (0, 0, img.width, img.height))
                chunk = KS_SYL[base:base+64]
                for k, ch in enumerate(chunk):
                    d.text((k*W + dx, dy), ch, font=f, fill=0)
                a = np.array(img) < 128
                for k in range(len(chunk)):
                    arrs[base+k] = a[:, k*W:(k+1)*W]
            temps.append(arrs.reshape(2350, -1))
    return np.stack(temps)  # (V, 2350, 192)

def match_and_dp(glyphs, anchors, tag, K=10, THRESH=0.55):
    """glyphs: {rank: bool-array}; anchors: {rank: char}"""
    ranks = sorted(glyphs)
    G = np.stack([glyphs[r].reshape(-1) for r in ranks]).astype(np.float32)  # (N,192)
    gsum = G.sum(1)
    temps = render_templates()  # (V,2350,192)
    V = temps.shape[0]
    best_scores = np.zeros((len(ranks), 2350), dtype=np.float32)
    for v in range(V):
        T = temps[v].astype(np.float32)          # (2350,192)
        inter = G @ T.T                           # (N,2350)
        tsum = T.sum(1)
        f1 = 2*inter / (gsum[:, None] + tsum[None, :] + 1e-6)
        np.maximum(best_scores, f1, out=best_scores)
    # 후보 추출
    cand = np.argsort(-best_scores, axis=1)[:, :K]
    # DP: KS 인덱스 엄격 증가, 점수합 최대, 스킵 허용(점수 0)
    items = []   # (glyph_i, ks_idx, score)
    for i, r in enumerate(ranks):
        if r in anchors:
            items.append((i, KS_IDX[anchors[r]], 100.0))
            continue
        for j in cand[i]:
            s = best_scores[i, j]
            if s >= THRESH:
                items.append((i, int(j), float(s)))
    # Fenwick(최대값) over KS index
    NK = 2350
    tree = [(-1.0, None)] * (NK + 1)
    def upd(pos, val):
        pos += 1
        while pos <= NK:
            if val[0] > tree[pos][0]:
                tree[pos] = val
            pos += pos & (-pos)
    def qry(pos):  # max over [0, pos]
        pos += 1
        best = (0.0, None)
        while pos > 0:
            if tree[pos][0] > best[0]:
                best = tree[pos]
            pos -= pos & (-pos)
        return best
    items.sort(key=lambda x: (x[0], x[1]))
    nodes = []
    from collections import defaultdict
    by_glyph = defaultdict(list)
    for gi, ks, s in items:
        by_glyph[gi].append((ks, s))
    for gi in sorted(by_glyph):
        new_nodes = []
        for ks, s in by_glyph[gi]:
            prev = qry(ks - 1) if ks > 0 else (0.0, None)
            total = prev[0] + s
            node = {'gi': gi, 'ks': ks, 's': s, 'total': total, 'prev': prev[1]}
            new_nodes.append(node)
        for node in new_nodes:
            upd(node['ks'], (node['total'], node))
            nodes.append(node)
    end = qry(NK - 1)
    result = {}
    node = end[1]
    while node is not None:
        result[ranks[node['gi']]] = KS_SYL[node['ks']]
        node = node['prev']
    # 앵커 검증
    for r, ch in anchors.items():
        assert result.get(r) == ch, (r, ch, result.get(r))
    scored = {ranks[i]: float(best_scores[i].max()) for i in range(len(ranks))}
    print(f'[{tag}] glyphs {len(ranks)}, identified {len(result)}, '
          f'unidentified {len(ranks)-len(result)}')
    return result, scored

def save(tag, result, glyphs, scored):
    with open(OUTD / f'{tag}_rank_to_hangul.tsv', 'w', encoding='utf-8') as f:
        f.write('rank\tchar\tmatch_score\n')
        for r in sorted(result):
            f.write(f'{r}\t{result[r]}\t{scored.get(r,0):.3f}\n')
    # 검수 시트: [글리프|매칭글자] 쌍
    ranks = sorted(glyphs)
    font = ImageFont.truetype(r'C:\Windows\Fonts\gulim.ttc', 12, index=1)
    cols, S = 16, 3
    rows_n = (len(ranks) + cols - 1) // cols
    cw, ch_ = (W*S + 30), (H*S + 18)
    img = Image.new('RGB', (cols*cw + 50, rows_n*ch_), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for k, r in enumerate(ranks):
        cx, cy = 50 + (k % cols)*cw, (k // cols)*ch_
        g = Image.fromarray((~glyphs[r] * 255).astype(np.uint8)).convert('L')
        img.paste(g.resize((W*S, H*S), Image.NEAREST).convert('RGB'), (cx, cy))
        ch2 = result.get(r, '·')
        d.text((cx + W*S + 3, cy + 6), ch2, font=font, fill=(200, 0, 0))
        if k % cols == 0:
            d.text((2, cy + 6), str(r), fill=(0, 0, 200))
    p = OUTD / f'{tag}_review.png'
    img.save(p)
    print('saved', p, img.size)

if __name__ == '__main__':
    # ---- Dra01 ----
    P1 = QN / 'work/patchers_extract/Dra01KoreanV3-0'
    big1 = (P1/'resources_BigFont').read_bytes()
    g1 = {r: glyph_arr(big1[r*26+2:r*26+26]) for r in range(234, 1090)}
    anchors1 = {257:'겐',336:'나',338:'난',388:'다',405:'데',407:'도',423:'둥',429:'드',
                468:'랙',510:'르',515:'리',522:'마',555:'몬',570:'미',596:'베',597:'벨',
                623:'블',663:'소',680:'스',705:'아',720:'야',763:'요',766:'우',781:'율',
                783:'으',786:'을',793:'일',879:'천',906:'카',910:'커',920:'코',937:'킨',
                965:'트',1002:'피'}
    r1, s1 = match_and_dp(g1, anchors1, 'dra01')
    save('dra01', r1, g1, s1)

    # ---- Dra02 ----
    P2 = QN / 'work/patchers_extract/Dra02KoreanV3-0'
    big2 = (P2/'resources_BigFont').read_bytes()
    g2 = {r: glyph_arr(big2[r*26+2:r*26+26]) for r in range(1330)}
    # 앵커: verify_d2에서 읽은 조나단/샬롯/윈드/빈센트 등은 rank를 아직 모름 -> DP만
    r2, s2 = match_and_dp(g2, {}, 'dra02')
    save('dra02', r2, g2, s2)
