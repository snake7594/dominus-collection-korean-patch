# -*- coding: utf-8 -*-
"""대사 추출: 현재 alldata.bin -> 편집용 TSV.

사용법:
  python extract.py dra01          # 한국어(패치) 텍스트
  python extract.py dra02
  python extract.py dra03          # 공식 한국어 (참고열: 일본어)
출력: pipeline/text/{game}_ko.tsv  (index / reference / text)
'text' 열만 수정하면 됨. 태그(<F006> 등)는 그대로 유지할 것.
"""
import sys, json, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *


def extract(game):
    TEXTDIR.mkdir(parents=True, exist_ok=True)
    f = open(ALLDATA, 'rb')
    cfg = GAMES[game]
    if game in ('dra01', 'dra02'):
        res = read_at(f, cfg['res0'], cfg['res_len'])
        entries = parse_resource(res)
        rank2ch, _, _ = build_decode_tables(game)
        texts = [decode_entry_ranked(t, rank2ch) for t in entries]
        refs = {r['index']: r['text'] for r in
                json.load(open(QN / cfg['ref_json'], encoding='utf-8'))}
    else:  # dra03: 공식 한국어 + 일본어 참조
        res = read_at(f, cfg['res_ko'], cfg['res_ko_len'])
        entries = parse_resource(res)
        texts = [decode_entry_euc(t) for t in entries]
        # 일본어 참조: dense rank + 선형 폰트 문자집합
        big = read_at(f, cfg['big']['NX'], cfg['big_size'])
        chains = scan_chains(big, 26)
        charset = [c for ch in chains for _, c in ch]
        assert all(a < b for a, b in zip(charset, charset[1:]))
        rank2ch = {i: c.to_bytes(2, 'big').decode('cp932')
                   for i, c in enumerate(charset)}
        res_ja = read_at(f, cfg['res_ja'], cfg['res_ja_len'])
        entries_ja = parse_resource(res_ja)
        refs = {i: decode_entry_ranked(t, rank2ch)
                for i, t in enumerate(entries_ja)}
    f.close()

    out = TEXTDIR / f'{game}_ko.tsv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as fo:
        w = csv.writer(fo, delimiter='\t', lineterminator='\n')
        w.writerow(['index', 'reference', 'text'])
        for i, t in enumerate(texts):
            w.writerow([i, refs.get(i, ''), t])
    print(f'{game}: {len(texts)} entries -> {out}')


if __name__ == '__main__':
    for g in (sys.argv[1:] or ['dra01', 'dra02', 'dra03']):
        extract(g)
