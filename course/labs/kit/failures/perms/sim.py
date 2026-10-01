#!/usr/bin/env python3
"""권한의 층 재현 — 실제 사용자 폴더는 건드리지 않고 sandbox 사본만 쓴다.

실제 형님 사건: macOS 폴더 권한 때문에 세션이 쓰기에 실패했다.
권한에는 층이 있다: ① 파일 모드(rwx) ② macOS TCC(앱별 접근 허용)
②' 앱 샌드박스(격리 컨테이너) ③ 도구의 승인 정책. ②와 ②'는 서로 다른 장치다.

이 스크립트는 kit 안의 sandbox/ 폴더만 만들고 chmod만 바꾼 뒤 되돌린다.
사용자의 실제 폴더·권한 설정은 바꾸지 않는다.

사용:
  python3 sim.py
"""
import os
import shutil
import stat
from pathlib import Path

SANDBOX = Path(__file__).parent / "sandbox"


def try_write(path):
    try:
        path.write_text("테스트")
        return "쓰기 성공"
    except PermissionError as e:
        return f"PermissionError(errno={e.errno})"


def main():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir()
    target = SANDBOX / "note.txt"

    print("1) 정상 폴더에 쓰기:")
    print("  ", try_write(target))

    # 읽기 전용으로 만든다(사본 sandbox 안에서만).
    SANDBOX.chmod(stat.S_IRUSR | stat.S_IXUSR)
    print("\n2) 폴더를 읽기 전용(r-x)으로 바꾼 뒤 새 파일 쓰기:")
    print("  ", try_write(SANDBOX / "new.txt"))
    print("   → 층1: 파일시스템 권한이 거절. 사용자가 '허용'한다고 뚫리지 않는다.")

    # 되돌린다 — cleanup 가능해야 하므로 반드시 복구.
    SANDBOX.chmod(stat.S_IRWXU)
    print("\n3) 권한을 되돌린 뒤 다시 쓰기:")
    print("  ", try_write(SANDBOX / "new.txt"))

    print("""
권한의 층(이 실습의 범위 안):
  층1 파일시스템 모드 — rwx 비트. 위에서 kit 사본으로 직접 재현.
  층2a macOS TCC — 'Documents 폴더 접근 허용' 같은 앱별 접근 허용.
  층2b 앱 샌드박스 — 앱이 격리 컨테이너 안에서만 파일을 보는 별도 장치.
        2a와 2b는 다르다. rwx가 맞아도 어느 쪽이든 막을 수 있다.
  층3 도구의 승인 정책 — CLI가 '이 명령 허용할까?' 묻는 층. OS 권한과 다르다.

판독: '권한 오류'를 봤을 때 어느 층인지 먼저 구분한다.
      층1은 errno/파일 모드, 2a는 TCC 설정, 2b는 샌드박스 프로파일,
      층3은 도구 승인 대화가 단서다.
      주의: 이 데모는 kit 사본의 rwx만 바꾼다 — 실제 TCC·샌드박스 동작을
      검증한 게 아니다. 2a/2b의 실증은 이 장치 범위 밖이다.
""")
    shutil.rmtree(SANDBOX)


if __name__ == "__main__":
    main()
