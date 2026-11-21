# daily-brief

Dan의 매일 아침 QQQ·QLD·TQQQ·BMNR 브리프용 스크립트. 예약 작업이 실행 때마다 이 저장소를 받아 씁니다.

- `daily_brief.py`: 매일 실행 스크립트 (가격·국면·위험·BMNR, 끝에 SNAPSHOT_JSON 출력)
- `regime.py`: 국면 판정 규칙 (regime-v1.1, 2026-11-21 고정)
- `mnav.py`: BMNR mNAV 계산기
- `score.py`: 채점값 계산 (10거래일 뒤 종가, 10일 중 최저 종가)

규칙이나 문턱을 바꾸면 버전을 올리고 커밋 메시지에 이유를 적습니다. 기록 시트의 스냅샷에 커밋 해시가 남아 어떤 규칙으로 판단했는지 추적할 수 있습니다.
