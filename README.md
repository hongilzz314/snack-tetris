# 과자 테트리스 (Tkinter + SQLite)

## 실행
Python 3.9 이상 권장. Windows Python 설치 시 Tkinter 포함 설치를 사용하세요.

```bash
python main.py
```

## 조작
- ← / → : 좌우 이동
- ↑ : 블록 회전
- ↓ : 빠른 하강
- Space : 즉시 하강
- P : 일시정지

## 과자 블록
막대과자, 초코쿠키, 젤리, 캐러멜, 초콜릿, 사탕, 웨하스 테마를 Canvas 도형으로 표현합니다. 별도 이미지/폰트/게임 라이브러리 없이 실행됩니다.


## DB
게임 기록은 사용자 홈 디렉터리의 `.snack_tetris/snack_tetris.db`에 저장됩니다. 게임 종료 시 이름, 점수, 제거한 줄, 레벨, 날짜를 기록합니다.


## Windows EXE 빌드
Windows에서 프로젝트 폴더 내 `build_exe.bat`를 더블 클릭하거나 아래 명령을 실행하세요.

```powershell
py -m pip install pyinstaller
py -m PyInstaller --clean --noconfirm --onefile --windowed --name SnackTetris main.py
```

결과 파일: `dist\SnackTetris.exe`


## 구성
- `main.py`: UI와 게임 로직
- `database.py`: SQLite 기록 저장/랭킹 조회
- `assets/game_over.png`: 사용자 교체 이미지
- `build_exe.bat`: Windows EXE 빌드 스크립트
