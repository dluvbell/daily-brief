import json, sys, urllib.request, argparse
import pandas as pd
H = {"User-Agent": "Mozilla/5.0"}
g = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30))

ap = argparse.ArgumentParser()
ap.add_argument("--eth", type=float, required=True, help="보유 ETH 수량 (최신 회사 발표)")
ap.add_argument("--shares", type=float, default=0, help="보통주 발행 주식 수 (가장 최근 공시값). 0이면 Yahoo 분기값 사용")
ap.add_argument("--cash", type=float, default=0, help="현금+유가증권 USD")
ap.add_argument("--btc", type=float, default=0, help="보유 BTC 수량")
ap.add_argument("--other", type=float, default=0, help="기타 지분(Beast, Eightco 등) USD 합")
ap.add_argument("--pref", type=float, default=0, help="우선주 청산가치 USD")
ap.add_argument("--liab", type=float, default=0, help="부채 USD")
a = ap.parse_args()

# BMNR 마지막 정규장 종가
r = g("https://query1.finance.yahoo.com/v8/finance/chart/BMNR?range=10d&interval=1d")["chart"]["result"][0]
idx = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
bc = pd.Series(r["indicators"]["quote"][0]["close"], index=idx).dropna()
price = bc.iloc[-1]; day = bc.index[-1].normalize()
t16 = day + pd.Timedelta(hours=15)  # 15:00~16:00 1시간봉의 종가 = 16:00 ET

def at16(sym):
    rr = g(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=10d&interval=1h")["chart"]["result"][0]
    i = pd.to_datetime(rr["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    s = pd.Series(rr["indicators"]["quote"][0]["close"], index=i).dropna()
    s = s[s.index <= t16]; return s.iloc[-1], s.index[-1]
eth_px, eth_t = at16("ETH-USD"); btc_px, _ = at16("BTC-USD")

# Yahoo 분기 발행주식 수 (참고/대체값)
ts = g("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/BMNR?type=quarterlyOrdinarySharesNumber&period1=1700000000&period2=1900000000")
vals = [v for v in ts["timeseries"]["result"][0].get("quarterlyOrdinarySharesNumber", []) if v]
y_sh, y_dt = (vals[-1]["reportedValue"]["raw"], vals[-1]["asOfDate"]) if vals else (None, None)
print(f"[Yahoo 분기 발행주식 수] {y_sh:,.0f}주 (기준 {y_dt}) - 분기말 값이라 이후 신주 발행/자사주 매입은 반영 안 됨" if y_sh else "[Yahoo 분기 발행주식 수] 못 구함")

shares = a.shares or y_sh
if not shares:
    print("[결과] 주식 수를 못 구해 mNAV 계산 불가 - 모름"); sys.exit(0)
src = "입력값(최근 공시)" if a.shares else f"Yahoo 분기값({y_dt})"
mcap = price * shares; ethv = a.eth * eth_px
nav = ethv + a.cash + a.btc * btc_px + a.other - a.pref - a.liab
print(f"[입력] BMNR 종가 ${price:.2f} ({day.date()} 16:00 ET) | ETH ${eth_px:,.2f} ({eth_t:%Y-%m-%d %H:%M} ET 시작 1시간봉 종가) | BTC ${btc_px:,.0f}")
print(f"[입력] 주식 수 {shares:,.0f} ({src}) | 보유 ETH {a.eth:,.0f}")
print(f"[결과] 시총 ${mcap/1e6:,.1f}M | ETH 가치 ${ethv/1e6:,.1f}M | mNAV(ETH만) {mcap/ethv:.3f} -> {'할인' if mcap < ethv else '프리미엄'} {abs(mcap/ethv-1)*100:.1f}%")
if any([a.cash, a.btc, a.other, a.pref, a.liab]):
    print(f"[결과] 넓은 NAV ${nav/1e6:,.1f}M (현금 {a.cash/1e6:.0f}M + BTC {a.btc*btc_px/1e6:.1f}M + 기타 {a.other/1e6:.0f}M - 우선주 {a.pref/1e6:.0f}M - 부채 {a.liab/1e6:.1f}M) | mNAV(넓은) {mcap/nav:.3f}")
print(f"[민감도] 주식 수 ±3%: mNAV(ETH만) {mcap*0.97/ethv:.3f} ~ {mcap*1.03/ethv:.3f}")
print(f"[손익분기] mNAV=1 되는 BMNR 가격: ETH만 ${ethv/shares:.2f}" + (f", 넓은 ${nav/shares:.2f}" if nav != ethv else ""))
print(f"[주당 ETH] 1,000주당 {a.eth/shares*1000:.3f} ETH")

# 실행 시각 기준(프리마켓/애프터 포함 마지막 체결) mNAV — 같은 보유량·주식 수, 가격만 현재값
def last_px(sym, pp):
    rr = g(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=5m{'&includePrePost=true' if pp else ''}")["chart"]["result"][0]
    i = pd.to_datetime(rr["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    s = pd.Series(rr["indicators"]["quote"][0]["close"], index=i).dropna(); return s.iloc[-1], s.index[-1]
try:
    bp, bt = last_px("BMNR", True); ep, et = last_px("ETH-USD", False); bp2 = last_px("BTC-USD", False)[0]
    mc2 = bp * shares; ev2 = a.eth * ep; nav2 = ev2 + a.cash + a.btc * bp2 + a.other - a.pref - a.liab
    print(f"[시간외] BMNR ${bp:.2f} ({bt:%m-%d %H:%M} ET) | ETH ${ep:,.2f} ({et:%m-%d %H:%M} ET) -> mNAV(ETH만) {mc2/ev2:.3f}"
          + (f" | mNAV(넓은) {mc2/nav2:.3f}" if nav2 != ev2 else "") + f" | 종가 기준 대비 할인 변화 {((mc2/nav2)-(mcap/nav))*100:+.1f}%p")
except Exception as e:
    print("[시간외] 못 구함:", type(e).__name__)
