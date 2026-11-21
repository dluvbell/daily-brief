# 국면 판정 규칙 (v1, 2026-11-21 고정). 문턱은 결과를 보기 전에 정한 둥근 숫자이며, 바꾸면 버전을 올리고 채점을 새로 시작한다.
import json, urllib.request
import numpy as np, pandas as pd

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
VERSION = "v1.1"  # v1.1(2026-11-21): 버그 수정만 - USDJPY 날짜 하루 미래 혼입 제거, 주봉 RSI 2주 지연 제거. 문턱 변경 없음

def _j(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=60).read())

def yfull(sym, adj=True, utc_date=False):
    for h in ("query1", "query2"):
        try:
            r = _j(f"https://{h}.finance.yahoo.com/v8/finance/chart/{sym}?period1=915148800&period2=4102444800&interval=1d")["chart"]["result"][0]
            i = pd.to_datetime(r["timestamp"], unit="s", utc=True)
            i = (i.tz_localize(None) if utc_date else i.tz_convert("America/New_York").tz_localize(None)).normalize()
            c = None
            if adj: c = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose")
            c = c or r["indicators"]["quote"][0]["close"]
            s = pd.Series(c, index=i, dtype="float64").dropna()
            return s[~s.index.duplicated(keep="last")]
        except Exception:
            continue
    return None

def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean(); l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + g / l)

def load():
    q = yfull("QQQ")
    raw = {k: yfull(s) for k, s in {"vix": "^VIX", "vix3m": "^VIX3M", "hyg": "HYG", "ief": "IEF",
                                    "ndx": "^NDX", "ndxe": "^NDXE", "sox": "^SOX"}.items()}
    # 외환: Yahoo 일봉 D는 UTC 00:00에 시작해 미국 장 마감 뒤에 끝남 -> UTC 날짜로 받고 하루 늦춰(D-1 봉을 D일에) 써야 미래 정보가 없음
    jp = yfull("JPY=X", utc_date=True); raw["jpy"] = None if jp is None else jp.shift(1)
    d = pd.DataFrame({"c": q})
    for k, s in raw.items():
        d[k] = s.reindex(d.index, method="ffill", limit=5) if s is not None else np.nan
    return d, [k for k, s in raw.items() if s is None]

def features(d):
    f = pd.DataFrame(index=d.index); c = d.c
    r1 = c.pct_change(); sd20 = r1.rolling(20).std()
    f["c"] = c; f["r1"] = r1; f["z"] = r1 / sd20.shift(1)
    f["r5"] = c / c.shift(5) - 1; f["r10"] = c / c.shift(10) - 1; f["r20"] = c / c.shift(20) - 1
    f["vol20"] = sd20 * np.sqrt(252)
    f["ma10"] = c.rolling(10).mean(); f["ma200"] = c.rolling(200).mean()
    f["ma200s"] = f.ma200 / f.ma200.shift(20) - 1
    f["dd252"] = c / c.rolling(252).max() - 1
    f["vix"] = d.vix; f["vr"] = d.vix / d.vix3m
    f["vrmax15"] = f.vr.shift(1).rolling(15).max()
    f["vix5"] = d.vix / d.vix.shift(5) - 1
    cr = d.hyg / d.ief; f["cr10"] = cr / cr.shift(10) - 1; f["cr60"] = cr / cr.shift(60) - 1
    f["jpy5"] = d.jpy / d.jpy.shift(5) - 1; f["jpy20"] = d.jpy / d.jpy.shift(20) - 1
    br = d.ndxe / d.ndx; f["br60"] = br / br.shift(60) - 1
    f["sox20"] = (d.sox / d.sox.shift(20)) / (c / c.shift(20)) - 1
    w = c.resample("W-FRI").last()
    f["wrsi"] = rsi(w).reindex(f.index, method="ffill")  # 금요일 종가까지의 주봉 RSI, 다음 주 월~목에 그대로 씀 (금요일 당일은 그 주 값: 종가 시점에 확정)
    y = np.log(c); x = pd.Series(np.arange(len(c)), index=c.index, dtype="float64"); n = 1260
    mx, my = x.rolling(n).mean(), y.rolling(n).mean()
    cov = (x * y).rolling(n).mean() - mx * my; vx = (x * x).rolling(n).mean() - mx ** 2; vy = (y * y).rolling(n).mean() - my ** 2
    b = cov / vx; resid = y - (my + b * (x - mx)); sres = np.sqrt((vy - b * cov).clip(lower=1e-12))
    f["trendz"] = resid / sres  # 5년 로그추세 대비 괴리 (표준편차 단위)
    f["band"] = 0.5 * f.vix / 100 * np.sqrt(10 / 252)  # 10거래일 ±0.5σ (VIX 내재변동성 기준, 예측 시점 값)
    return f

def tactical(r):
    """우선순위 T1 > T2 > T4 > T3. 입력 r = features의 한 행."""
    if r.vr >= 1.0 and (r.cr10 <= -0.02 or r.jpy5 <= -0.03) and (r.r10 <= -0.05 or r.z <= -2.5):
        return "T1 강제청산"
    if r.vrmax15 >= 1.0 and r.vr < 0.95 and r.c > r.ma10:
        return "T2 소진·회복"
    hot = sum([r.c / r.ma200 >= 1.12, r.wrsi >= 70, (r.vol20 < 0.15 and r.r20 >= 0.05), (r.r5 >= 0.03 and r.vix5 >= 0.10)])
    if hot >= 2:
        return "T4 상승 과열"
    return "T3 중립"

def structural(r):
    """우선순위 S3 > S2 > S1."""
    if r.dd252 <= -0.15 or (r.c < r.ma200 and r.ma200s < 0) or r.cr60 <= -0.04:
        return "S3 손상"
    if r.c / r.ma200 >= 1.15 or (r.trendz >= 1.5 and r.br60 < 0):
        return "S2 과열"
    return "S1 정상"

def attrs(r):
    a = []
    if r.c < r.ma200: a.append("200일선 아래")
    if r.vr >= 1.0: a.append("VIX 기간구조 역전")
    if r.cr10 <= -0.02: a.append("신용 10일 악화")
    if r.jpy5 <= -0.03: a.append("엔화 급강세(캐리 청산 위험)")
    if r.r5 >= 0.03 and r.vix5 >= 0.10: a.append("가격·VIX 동반 상승(기계적 상승 의심)")
    return a

def slow_alarms(r):
    a = []
    if r.cr60 <= -0.03: a.append(f"신용(HYG/IEF) 60일 {r.cr60*100:+.1f}%")
    if r.jpy20 <= -0.05: a.append(f"USDJPY 20일 {r.jpy20*100:+.1f}%")
    if r.br60 <= -0.05: a.append(f"시장 폭(동일가중/시총가중) 60일 {r.br60*100:+.1f}%")
    if r.sox20 <= -0.10: a.append(f"반도체 상대강도 20일 {r.sox20*100:+.1f}%")
    return a

def label(f):
    ok = f.dropna(subset=["vr", "cr60", "trendz", "br60", "ma200s", "wrsi", "jpy5", "z", "vrmax15"])
    t = ok.apply(tactical, axis=1); s = ok.apply(structural, axis=1)
    return t, s

def probs(sub, fwd, band):
    up = (fwd[sub] > band[sub]).mean(); dn = (fwd[sub] < -band[sub]).mean()
    return up, 1 - up - dn, dn

def episodes(idx, gap=15):
    if len(idx) == 0: return 0
    s = pd.Series(idx).diff().dt.days
    return int((s > gap).sum() + 1)

def mode_flags(F):
    """깊은 모드 트리거 (켜지는 날만): 마지막 행 기준. F에는 features + T, S 열이 있어야 함."""
    r, y = F.iloc[-1], F.iloc[-2]; fl = []
    if abs(r.z) >= 2.5: fl.append(f"하루 변동 {r.z:.1f}σ")
    if r["T"] == "T1 강제청산": fl.append("T1 강제청산")
    for lv in (25, 30, 40):
        if r.vix >= lv > y.vix: fl.append(f"VIX {lv} 상향 돌파")
    old_keys = set(a.split(" ")[0] for a in slow_alarms(y))
    fl += ["새 느린 경보: " + a for a in slow_alarms(r) if a.split(" ")[0] not in old_keys]
    for col in ("T", "S"):  # 국면 전환은 새 국면이 3거래일 연속 유지된 날 한 번만
        s = F[col].iloc[-4:]
        if len(s) == 4 and s.iloc[1] == s.iloc[2] == s.iloc[3] != s.iloc[0]: fl.append(f"{col} 국면 전환 확정: {s.iloc[0]} -> {s.iloc[3]}")
    return fl
