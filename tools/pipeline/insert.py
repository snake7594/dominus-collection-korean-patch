# -*- coding: utf-8 -*-
"""수정한 TSV를 alldata.bin에 재삽입.

사용법:
  python insert.py dra03              # pipeline/text/dra03_ko.tsv 적용
  python insert.py dra01 dra02 dra03  # 여러 개
  python insert.py dra03 --no-backup

동작:
- TSV의 'text' 열을 인코딩해 리소스(count+table+text)를 재구성, 원 크기 예산 검사
- dra01/02: 폰트에 없는 한글이 나오면 여유 슬롯에 굴림체 글리프를 생성해 주입
  (큰폰트 NX/PS5/WIN + 작은폰트 NX/PS5 + WIN 8x8 섹션), 한글표 TSV 갱신
- alldata.bin 백업 후 제자리 기록
"""
import sys, csv, shutil, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *


def gen_glyph_big(ch):
    """굴림체 12px -> 16x12 1bpp(24B)."""
    from PIL import Image, ImageFont, ImageDraw
    f = ImageFont.truetype(r'C:\Windows\Fonts\gulim.ttc', 12, index=1)
    img = Image.new('L', (16, 12), 255)
    ImageDraw.Draw(img).text((0, 0), ch, font=f, fill=0)
    a = img.point(lambda v: 0 if v < 128 else 255, '1')
    out = bytearray()
    px = a.load()
    for r in range(12):
        row = 0
        for x in range(16):
            if px[x, r] == 0:
                row |= 0x8000 >> x
        out += row.to_bytes(2, 'big')
    return bytes(out)


def gen_glyph_small(ch):
    """8x8 1bpp(8B): 굴림 11px 렌더 후 8x8 축소."""
    from PIL import Image, ImageFont, ImageDraw
    f = ImageFont.truetype(r'C:\Windows\Fonts\gulim.ttc', 11, index=1)
    img = Image.new('L', (12, 12), 255)
    ImageDraw.Draw(img).text((0, 0), ch, font=f, fill=0)
    img = img.resize((8, 8), Image.LANCZOS)
    a = img.point(lambda v: 0 if v < 150 else 255, '1')
    out = bytearray()
    px = a.load()
    for r in range(8):
        row = 0
        for x in range(8):
            if px[x, r] == 0:
                row |= 0x80 >> x
        out.append(row)
    return bytes(out)


class FontSlots:
    """dra01/02 폰트 5개 위치(빅 NX/PS5/WIN26B/WIN8x8, 스몰 NX/PS5)에 신규 글리프 기록."""
    def __init__(self, f, game):
        self.f = f
        self.game = game
        cfg = GAMES[game]
        self.cfg = cfg
        n = cfg['charset_n']
        # 각 폰트의 rank->비트맵 오프셋 (현재 파일에서 체인 재스캔)
        self.pos = {}
        for var, off in cfg['big'].items():
            dat = read_at(f, off, cfg['big_size'])
            if var == 'WIN':
                ch26 = [c for c in scan_chains(dat, 26) if len(c) >= 15]
                base = {}
                first = ch26[0]
                first_rank = n - len(first)          # 한자 섹션 = 뒤쪽 rank
                for k, (o, _) in enumerate(first):
                    base[first_rank + k] = o
                self.pos[('big26', var)] = (off, base)
                ch10 = [c for c in scan_chains(dat, 10) if len(c) == n]
                b10 = ch10[0][0][0]
                self.pos[('win8', var)] = (off, {r: b10 + 10*r for r in range(n)})
            else:
                chains = [c for c in scan_chains(dat, 26) if len(c) >= 15]
                allpos = {}
                r = 0
                for ch in chains:
                    for o, _ in ch:
                        allpos[r] = o; r += 1
                self.pos[('big26', var)] = (off, allpos)
        for var, off in cfg['small'].items():
            dat = read_at(f, off, cfg['small_size'])
            chains = [c for c in scan_chains(dat, 10) if len(c) >= 15]
            # 문자집합 대조로 rank 부여
            bigNX = read_at(f, cfg['big']['NX'], cfg['big_size'])
            cs = [c for ch in scan_chains(bigNX, 26) if len(ch) >= 15 for _, c in ch]
            rank_of = {c: i for i, c in enumerate(cs)}
            allpos = {}
            for ch in chains:
                for o, c in ch:
                    if c in rank_of:
                        allpos[rank_of[c]] = o
            self.pos[('small', var)] = (off, allpos)

    def write_glyph(self, rank, ch):
        big = gen_glyph_big(ch)
        small = gen_glyph_small(ch)
        for (kind, var), (off, table) in self.pos.items():
            if rank not in table:
                continue
            o = table[rank]
            if kind == 'big26':
                if o + 26 > self.cfg['big_size']:
                    continue
                self.f.seek(off + o + 2); self.f.write(big)
            elif kind == 'win8':
                if o + 10 > self.cfg['big_size']:
                    continue
                self.f.seek(off + o + 2); self.f.write(small)
            elif kind == 'small':
                if o + 10 > self.cfg['small_size']:
                    continue
                self.f.seek(off + o + 2); self.f.write(small)


def insert(game, backup=True):
    cfg = GAMES[game]
    tsv = TEXTDIR / f'{game}_ko.tsv'
    rows = list(csv.reader(open(tsv, encoding='utf-8-sig'), delimiter='\t'))[1:]
    cnt_expected = cfg['count']
    assert len(rows) == cnt_expected, f'entry 수 불일치: {len(rows)} != {cnt_expected}'
    texts = {int(r[0]): (r[2] if len(r) > 2 else '') for r in rows}

    f = open(ALLDATA, 'r+b')

    if game == 'dra03':
        entries = [encode_text(texts[i]) for i in range(cnt_expected)]
        res, total = rebuild_resource(entries, cfg['res_ko_len'], cnt_expected)
        target, budget = cfg['res_ko'], cfg['res_ko_len']
    else:
        rank2ch, ch2rank, _ = build_decode_tables(game)
        # 신규 한글 할당 준비
        slots = None
        used_free = {}
        # 최종 데이터에서 이미 참조되는 rank 는 free 에서 제외
        pending_ranks = set()
        def new_alloc(ch):
            nonlocal slots
            if ch in used_free:
                return used_free[ch]
            for r in cfg['free_ranks']:
                if r in used_free.values() or r in pending_ranks:
                    continue
                used_free[ch] = r
                return r
            raise ValueError('여유 폰트 슬롯 소진')
        # 1차 인코딩 (신규 글자 수집)
        entries = []
        for i in range(cnt_expected):
            try:
                entries.append(encode_text(texts[i], ch2rank, new_alloc))
            except ValueError as e:
                raise SystemExit(f'entry {i} 인코딩 실패: {e}')
        # 기존 토큰과 충돌 검사: free rank 코드가 이미 쓰였는지
        used_tokens = {t for ent in entries for t in ent}
        for ch, r in used_free.items():
            code = rank_to_code(r)
            # 그 rank가 신규 할당 이전 텍스트에 존재했다면 문제 -> free 목록 특성상 없음
        res, total = rebuild_resource(entries, cfg['res_len'], cnt_expected)
        target, budget = cfg['res0'], cfg['res_len']
        # 신규 글리프 주입 + 한글표 갱신
        if used_free:
            slots = FontSlots(f, game)
            for ch, r in sorted(used_free.items(), key=lambda x: x[1]):
                slots.write_glyph(r, ch)
            hp = QN / 'work/claude_mapping' / cfg['hangul_tsv']
            with open(hp, 'a', encoding='utf-8') as hf:
                for ch, r in sorted(used_free.items(), key=lambda x: x[1]):
                    hf.write(f'{r}\t{ch}\t1.000\n')
            print(f'{game}: 신규 글리프 {len(used_free)}자 주입: '
                  + ''.join(sorted(used_free)))

    if backup:
        bak = ALLDATA.with_name(f'alldata.backup-{time.strftime("%Y%m%d-%H%M%S")}.bin')
        f.close()
        shutil.copyfile(ALLDATA, bak)
        print('backup:', bak.name)
        f = open(ALLDATA, 'r+b')

    f.seek(target)
    f.write(res)
    f.close()
    print(f'{game}: {cnt_expected} entries 기록 ({total}/{budget} bytes, '
          f'여유 {budget-total})')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    backup = '--no-backup' not in sys.argv
    done_backup = False
    for g in args:
        insert(g, backup=backup and not done_backup)
        done_backup = True
