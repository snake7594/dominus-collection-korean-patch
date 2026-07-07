#!/usr/bin/env python3
"""Castlevania Dominus Collection (Steam 최신판) 한글 개선패치 적용.

이 패치는 **한글 베이스 패치(Dra01/Dra02KoreanV4)가 적용된** 최신 Steam
alldata.bin 에 얹는 '개선 패치'입니다. (dra03 영문 고유명사 한글화 + 오타/미번역 수정)

사용법:
  pip install pyxdelta
  python apply_patch.py "C:\\...\\Castlevania Dominus Collection\\windata\\alldata.bin"

동작: 베이스(V4) 해시 확인 -> 개선본 생성 -> 원본을 .bak 로 백업 후 교체.
게임 데이터는 저장소에 포함돼 있지 않습니다.
"""
import sys, os, hashlib, shutil

PATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DominusKorean_Steam_v2.xdelta')
BASE_SHA1 = 'ba2377dd7ce22896723b8de5c9000e067d1c8b95'   # V4 한글 적용 상태
BASE_SIZE = 1279606784
OUT_SHA1  = '9d04a391ce71b032934da3614990c6776135aad2'   # 개선 적용 후


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    if not os.path.exists(src):
        print(f'[!] alldata.bin 을 찾을 수 없습니다: {src}'); sys.exit(1)
    if os.path.getsize(src) != BASE_SIZE:
        print('[!] 파일 크기가 예상과 다릅니다.')
        print('    - 최신 Steam 버전인지, 한글패치(V4)가 적용됐는지 확인하세요.'); sys.exit(1)
    print('[*] 베이스(V4 한글) 해시 확인 중...')
    cur = sha1(src)
    if cur == OUT_SHA1:
        print('[=] 이미 개선패치가 적용된 파일입니다. 종료.'); sys.exit(0)
    if cur != BASE_SHA1:
        print('[!] 베이스 해시가 일치하지 않습니다.')
        print('    이 패치는 Dra01/Dra02KoreanV4 한글패치가 적용된 최신 Steam alldata.bin 전용입니다.')
        print(f'    (기대 {BASE_SHA1}, 현재 {cur})'); sys.exit(1)
    try:
        import pyxdelta
    except ImportError:
        print('[!] pyxdelta 미설치.  실행:  pip install pyxdelta'); sys.exit(1)
    out = src + '.improved.tmp'
    print('[*] 개선 패치 적용 중...')
    if not pyxdelta.decode(src, PATCH, out):
        print('[!] 적용 실패'); sys.exit(1)
    if sha1(out) != OUT_SHA1:
        print('[!] 결과 해시 불일치'); os.remove(out); sys.exit(1)
    bak = src + '.bak'
    if not os.path.exists(bak):
        shutil.copyfile(src, bak); print(f'[*] 원본 백업: {bak}')
    os.replace(out, src)
    print('[OK] 개선패치 적용 완료!')
    print('     창월/각인 = 게임 언어 "일본어", 에클레시아 = "한국어"로 플레이하세요.')


if __name__ == '__main__':
    main()
