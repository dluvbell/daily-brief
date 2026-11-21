# 채점값 계산: python3 -I score.py QQQ 2026-11-20 2026-11-21 ...  (BMNR도 같은 방식)
# 각 기준 종가일마다: 10거래일 뒤 날짜와 종가, 1~10거래일 동안 최저 종가. 아직 10거래일이 안 지났으면 '미확정'.
import json, sys, urllib.request
import pandas as pd
H = {"User-Agent": "Mozilla/5.0"}
sym, dates = sys.argv[1], sys.argv[2:]
for h in ("query1", "query2"):
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://{h}.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d", headers=H), timeout=30))["chart"]["result"][0]
        break
    except Exception:
        r = None
if r is None:
    print(json.dumps({"오류": "Yahoo 실패"}, ensure_ascii=False)); sys.exit(0)
i = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
c = pd.Series(r["indicators"]["quote"][0]["close"], index=i).dropna(); c = c[~c.index.duplicated(keep="last")]
now = pd.Timestamp.now(tz="America/New_York")
if c.index[-1] == now.tz_localize(None).normalize() and now.hour * 60 + now.minute < 16 * 60 + 15:
    c = c.iloc[:-1]  # 장중 실행이면 아직 확정되지 않은 오늘 봉 제외
out = {}
for d in dates:
    t = pd.Timestamp(d)
    if t not in c.index:
        out[d] = "기준일이 거래일 목록에 없음"; continue
    k = c.index.get_loc(t)
    if k + 10 >= len(c):
        out[d] = f"미확정 ({len(c) - 1 - k}거래일 지남)"; continue
    w = c.iloc[k + 1:k + 11]
    out[d] = {"채점일": str(w.index[-1].date()), "채점일 종가": round(float(w.iloc[-1]), 4), "10일 중 최저 종가": round(float(w.min()), 4)}
print(json.dumps(out, ensure_ascii=False))
