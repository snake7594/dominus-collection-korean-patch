#!/usr/bin/env python3
"""Castlevania Dominus Collection 한글패치 적용 스크립트.

사용법:  python apply_patch.py "C:\\...\\Castlevania Dominus Collection\\windata\\alldata.bin"

필요:  pip install pyxdelta
원본(무수정) alldata.bin에만 적용됩니다 (해시 검증).
게임 데이터는 이 저장소에 포함되어 있지 않습니다.
"""
import sys, os, hashlib, shutil

PATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DominusKorean_v1.xdelta')
SRC_SHA1 = '45a7bb1dc98e01b0e55c0038f1f9357048944a8a'
SRC_SIZE = 853831680
OUT_SHA1 = 'bec42de24b887c446e94d02d0a0555d02aec2ec2'


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    if not os.path.exists(src):
        print(f'[!] alldata.bin 을 찾을 수 없습니다: {src}')
        sys.exit(1)
    if os.path.getsize(src) != SRC_SIZE:
        print('[!] 파일 크기가 원본과 다릅니다. 이미 패치되었거나 다른 버전입니다.')
        sys.exit(1)
    print('[*] 원본 해시 확인 중...')
    if sha1(src) != SRC_SHA1:
        print('[!] SHA1 불일치 — 무수정 원본이 아닙니다.')
        sys.exit(1)
    try:
        import pyxdelta
    except ImportError:
        print('[!] pyxdelta가 없습니다.  실행:  pip install pyxdelta')
        sys.exit(1)
    out = src + '.korean.tmp'
    print('[*] 패치 적용 중...')
    if not pyxdelta.decode(src, PATCH, out):
        print('[!] 패치 적용 실패')
        sys.exit(1)
    print('[*] 결과 해시 확인 중...')
    if sha1(out) != OUT_SHA1:
        print('[!] 결과 해시 불일치')
        sys.exit(1)
    bak = src + '.bak'
    if not os.path.exists(bak):
        print(f'[*] 원본 백업: {bak}')
        shutil.move(src, bak)
    else:
        os.remove(src)
    shutil.move(out, src)
    print('[OK] 한글패치 적용 완료!')
    print('     창월/각인 = 게임 언어 "일본어", 에클레시아 = "한국어"로 플레이하세요.')


if __name__ == '__main__':
    main()
