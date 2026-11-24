import json, urllib.request, datetime as dt, io, zipfile, warnings
import pandas as pd
warnings.filterwarnings("ignore")
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
def raw(u, t=60): return urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=t).read()
def j(u): return json.loads(raw(u, 30))

def yahoo(sym, rng="2y"):
    for h in ("query1", "query2"):
        try:
            r = j(f"https://{h}.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d")["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            idx = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
            df = pd.DataFrame({k: q[k] for k in ["open", "high", "low", "close", "volume"]}, index=idx).dropna(subset=["close"])
            return df[~df.index.duplicated(keep="last")]
        except Exception:
            continue
    return None

def nasdaq(sym):
    try:
        t = dt.date.today(); f = t - dt.timedelta(days=14)
        rows = j(f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass=etf&fromdate={f}&limit=15&todate={t}")["data"]["tradesTable"]["rows"]
        return {pd.to_datetime(r["date"]).normalize(): (float(r["close"].replace("$", "").replace(",", "")), int(r["volume"].replace(",", ""))) for r in rows}
    except Exception:
        return None

def rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean(); l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + g / l)

R, D = {}, {}
for s in ["QQQ", "QLD", "TQQQ"]:
    df = yahoo(s)
    if df is None:
        print(f"[{s}] 데이터 못 구함 (Yahoo 실패)"); continue
    nq = nasdaq(s); D[s] = df
    c = df.close; last = c.index[-1]; p = c.iloc[-1]
    if not nq: chk = "백업 없음(Nasdaq 실패)"
    elif last not in nq: chk = "날짜 불일치(Nasdaq에 해당일 없음)"
    else:
        diff = abs(nq[last][0] / p - 1) * 100
        chk = f"OK(차이 {diff:.2f}%)" if diff <= 0.5 else f"불일치({diff:.2f}%) - 판정 보류"
    w = c.resample("W-FRI").last().dropna()
    prior = df.iloc[-21:-1]; r6 = df.iloc[-127:-1]
    ma50 = c.rolling(50).mean().iloc[-1]; ma200 = c.rolling(200).mean().iloc[-1]
    vol = nq[last][1] if nq and last in nq else df.volume.iloc[-1]
    rng = df.high.iloc[-1] - df.low.iloc[-1]
    res = sorted(x for x in [ma50, ma200, prior.high.max(), r6.high.max()] if x > p)
    R[s] = dict(last=last, p=p, prev=c.iloc[-2], chg=c.pct_change().iloc[-1]*100,
        r5=(p/c.iloc[-6]-1)*100, r1=(p/c.iloc[-22]-1)*100, r3=(p/c.iloc[-64]-1)*100, r6=(p/c.iloc[-127]-1)*100,
        ytd=(p/c[c.index < dt.datetime(last.year, 1, 1)].iloc[-1]-1)*100, ma50=ma50, ma200=ma200,
        rd=rsi(c).iloc[-1], rw=rsi(w).iloc[-1], volx=vol/df.volume.iloc[-21:-1].mean(),
        wick=(min(df.open.iloc[-1], p)-df.low.iloc[-1])/rng if rng > 0 else 0, low=df.low.iloc[-1],
        sup20=prior.low.min(), sup6=r6.low.min(), hi20=prior.high.max(), hi6=r6.high.max(),
        res=res[0] if res else None, chk=chk)

def verdict(r):
    if "불일치" in r["chk"]: return "판정 보류 (데이터 불일치)"
    if r["low"] < r["sup20"] or r["p"] < r["sup20"]: return "아직 하락 중 (직전 20일 저점 이탈/신저점)"
    if r["res"] is not None and r["p"] > r["prev"] and r["volx"] > 1.0 and r["p"] > r["res"]: return "반등 확정"
    if r["res"] is None and r["p"] > r["prev"] and r["volx"] > 1.0: return "반등 확정 (위 저항 없음)"
    if r["rd"] < 30 and r["wick"] >= 0.3: return "반등 시도 중 (과매도+아래꼬리, 저항 아래)"
    return "규칙상 해당 없음 (중립)"

if R:
    k0 = next(iter(R))
    print(f"=== 출처: Yahoo Finance 일봉(query1/2), 교차검증 Nasdaq API | 기준: {R[k0]['last'].date()} 정규장 종가(ET 16:00) ===")
for s, r in R.items():
    print(f"\n[{s}] 종가 {r['p']:.2f} ({r['chg']:+.2f}%) | 교차검증 {r['chk']}")
    print(f" 수익률 5일 {r['r5']:+.1f}% / 1M {r['r1']:+.1f}% / 3M {r['r3']:+.1f}% / 6M {r['r6']:+.1f}% / YTD {r['ytd']:+.1f}%")
    print(f" MA50 {r['ma50']:.2f}({'위' if r['p']>r['ma50'] else '아래'}) / MA200 {r['ma200']:.2f}({'위' if r['p']>r['ma200'] else '아래'})")
    print(f" RSI(14) 일 {r['rd']:.1f} / 주 {r['rw']:.1f} | 거래량 20일평균 대비 {r['volx']:.2f}x | 아래꼬리 비율 {r['wick']:.2f}")
    res = f"{r['res']:.2f}" if r['res'] else "없음"
    print(f" 지지: 직전20일 저점 {r['sup20']:.2f} / 6M 저점 {r['sup6']:.2f} (당일 저점 {r['low']:.2f}) | 저항: 가장 가까운 {res}, 20일고점 {r['hi20']:.2f}, 6M고점 {r['hi6']:.2f}")
    print(" 규칙 판정:", verdict(r))

if all(k in D for k in ("QQQ", "QLD", "TQQQ")):
    q = D["QQQ"].close
    print("\n[같은날 등락 1x/2x/3x] " + " / ".join(f"{s} {R[s]['chg']:+.2f}%" for s in R))
    print(" 최근 5일 일별(QQQ/QLD/TQQQ):")
    t = pd.DataFrame({s: D[s].close.pct_change()*100 for s in R}).iloc[-5:]
    for d_, row in t.iterrows(): print(f"  {d_.date()} " + " / ".join(f"{v:+.2f}%" for v in row))
    for s, k in (("QLD", 2), ("TQQQ", 3)):
        a = D[s].close; g = []
        for n in (20, 60, 126):
            g.append(f"{n}일 {((a.iloc[-1]/a.iloc[-1-n]-1) - (q.iloc[-1]/q.iloc[-1-n]-1)*k)*100:+.1f}%p")
        print(f" {s} 실제-단순{k}배 누적 갭(음수=소멸): " + ", ".join(g))
    qq = q.iloc[-21:]; rng20 = (qq.max()/qq.min()-1)*100; net20 = (qq.iloc[-1]/qq.iloc[0]-1)*100
    print(f" QQQ 20일 변동폭 {rng20:.1f}% vs 순변화 {net20:+.1f}% (폭 크고 순변화 작으면 횡보형 소멸 구간)")

CTX = {}
print("\n[시장 맥락 - Yahoo]")
for n, sy in (("VIX", "^VIX"), ("VIX3M", "^VIX3M"), ("미10년물", "^TNX"), ("달러지수", "DX-Y.NYB"), ("USDJPY", "JPY=X"),
              ("나스닥선물", "NQ=F"), ("반도체SOX", "^SOX"), ("S&P500", "^GSPC")):
    d = yahoo(sy, "1mo")
    if d is None or len(d) < 6: print(f" {n}: 못 구함"); continue
    c = d.close; CTX[n] = round(float(c.iloc[-1]), 4); print(f" {n} {c.iloc[-1]:.2f} ({c.pct_change().iloc[-1]*100:+.2f}%, 5일 {(c.iloc[-1]/c.iloc[-6]-1)*100:+.1f}%) 기준 {d.index[-1].date()}")
try:
    v = yahoo("^VIX", "5d").close.iloc[-1]; v3 = yahoo("^VIX3M", "5d").close.iloc[-1]
    print(f" VIX/VIX3M {v/v3:.2f} ({'역전=단기 공포 극단' if v > v3 else '정상'})")
except Exception: pass

print("\n[QQQ 상위 종목 당일]")
out = []
for sy in ("NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "AVGO", "TSLA"):
    d = yahoo(sy, "5d")
    out.append(f"{sy} {d.close.pct_change().iloc[-1]*100:+.1f}%" if d is not None and len(d) > 1 else f"{sy} 못 구함")
print(" " + " | ".join(out))

print("\n[CFTC TFF - 나스닥100 E-mini, 순포지션 = 롱-숏, 3년 백분위]")
try:
    yr = dt.date.today().year; fr = []
    for y in range(yr-3, yr+1):
        try:
            z = zipfile.ZipFile(io.BytesIO(raw(f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{y}.zip", 120)))
            fr.append(pd.read_csv(z.open(z.namelist()[0]), low_memory=False))
        except Exception: pass
    d = pd.concat(fr); m = d[d["Market_and_Exchange_Names"].str.contains("NASDAQ MINI", case=False)].copy()
    m["dt"] = pd.to_datetime(m["Report_Date_as_YYYY-MM-DD"]); m = m.drop_duplicates("dt").sort_values("dt")
    print(f" 기준일 {m.dt.iloc[-1].date()}(화요일 기준, 금요일 공개) | OI {int(m.Open_Interest_All.iloc[-1]):,}")
    for k, pfx in (("자산운용사", "Asset_Mgr"), ("레버리지펀드", "Lev_Money"), ("딜러", "Dealer")):
        net = m[pfx+"_Positions_Long_All"] - m[pfx+"_Positions_Short_All"]
        print(f" {k}: 순 {int(net.iloc[-1]):+,} (전주 {int(net.iloc[-2]):+,}, 4주전 {int(net.iloc[-5]):+,}) | 3년 백분위 {(net < net.iloc[-1]).mean()*100:.0f}")
except Exception as e:
    print(" 못 구함:", type(e).__name__)


import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime as RG
SNAP = {"버전": "brief-v2.1 / regime-v1.1 / risk-logit-v1", "기준일": str(R[next(iter(R))]["last"].date()) if R else None,
        "종목": {s: {k: (round(float(v), 4) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in r.items()} for s, r in R.items()},
        "맥락": CTX}
def fwd_min(s, n):  # 앞으로 n거래일 중 최저 종가 / 오늘 - 1 (n일이 다 지나야 값이 생김)
    return pd.concat([s.shift(-k) for k in range(1, n + 1)], axis=1).min(axis=1, skipna=False) / s - 1
def ud(s, col="fwd"):
    u = (s[col] > s.band).mean(); d_ = (s[col] < -s.band).mean(); return u, 1 - u - d_, d_
fmt = lambda p: f"상승 {p[0]*100:.0f}% / 보합 {p[1]*100:.0f}% / 하락 {p[2]*100:.0f}%"

print("\n[방향 확률 - QQQ 10거래일 뒤 | 보합 = ±0.5σ, σ = 오늘 VIX로 본 10일 변동폭]")
print(" 주의: 2020~2026 표본 밖 검증에서 유사국면·국면 확률 모두 기저율을 의미 있게 못 이겼음 -> 방향 확률은 참고·기록용")
try:
    qf = RG.yfull("QQQ"); vf = RG.yfull("^VIX").reindex(qf.index).ffill()
    a = pd.DataFrame({"c": qf, "vix": vf}); a["rsi"] = rsi(qf); a["ma200"] = qf.rolling(200).mean()
    a["dd20"] = qf / qf.rolling(20).max() - 1; a["fwd"] = qf.shift(-10) / qf - 1; a["mdd10"] = fwd_min(qf, 10)
    a["band"] = 0.5 * a.vix / 100 * np.sqrt(10 / 252)
    x = a.iloc[-1]; h = a.dropna(subset=["fwd", "ma200", "mdd10"])
    print(f" 오늘 보합 범위: ±{x.band*100:.1f}% (10일 1σ ±{x.band*200:.1f}%)")
    pb = ud(h); rb_ = (h.mdd10 <= -0.05).mean()
    print(f" 기저율(1999~ 모든 날): {fmt(pb)} | 10일 안 -5% 이상 하락 {rb_*100:.0f}%")
    b_r = lambda v: 0 if v < 30 else 1 if v < 40 else 2 if v < 60 else 3
    b_v = lambda v: 0 if v < 20 else 1 if v < 30 else 2
    b_d = lambda v: 0 if v > -0.05 else 1 if v > -0.10 else 2
    conds = [("RSI구간", lambda d: d.rsi.map(b_r) == b_r(x.rsi)), ("200일선 위/아래", lambda d: (d.c < d.ma200) == (x.c < x.ma200)),
             ("20일고점 대비 낙폭", lambda d: d.dd20.map(b_d) == b_d(x.dd20)), ("VIX구간", lambda d: d.vix.map(b_v) == b_v(x.vix))]
    print(f" 현재 상태: RSI {x.rsi:.1f}, 200일선 {'아래' if x.c < x.ma200 else '위'}, 20일고점 대비 {x.dd20*100:.1f}%, VIX {x.vix:.1f}")
    best = None
    for k in range(len(conds), 0, -1):
        m = np.ones(len(h), bool)
        for _, f in conds[:k]: m &= f(h).values
        s = h[m]
        if len(s) == 0: continue
        ep = int((s.index.to_series().diff().dt.days > 15).sum() + 1); p = ud(s); rk = (s.mdd10 <= -0.05).mean()
        print(f" 유사국면 조건 {k}개: 표본 {len(s)}일/독립국면 {ep}개 | {fmt(p)} | 10일 안 -5% 하락 {rk*100:.0f}% | 중앙값 {s.fwd.median()*100:+.1f}%")
        if best is None and ep >= 10: best = (k, ep, p, rk)
    if best:
        print(f" => 유사국면 대표값(조건 {best[0]}개, 국면 {best[1]}개): {fmt(best[2])} | 위험 {best[3]*100:.0f}%")
        SNAP["QQQ 유사국면"] = {"조건수": best[0], "국면수": best[1], "확률": [round(v, 3) for v in best[2]], "위험_-5%": round(best[3], 3)}
    else: print(" => 독립국면 10개 이상인 조건 없음: 확률 신뢰 낮음")
    SNAP["QQQ 기저율"] = {"확률": [round(v, 3) for v in pb], "위험_-5%": round(rb_, 3), "보합범위": round(float(x.band), 4)}
except Exception as e:
    print(" 못 구함:", type(e).__name__, e)

print("\n[국면·위험 - 규칙 regime-v1.1 (2026-11-21 고정, 결과를 보기 전에 정한 문턱) | 위험 = 10거래일 안 QQQ 종가가 -5% 이상 하락]")
DEEP = []
try:
    d_, miss = RG.load(); F = RG.features(d_); T_, S_ = RG.label(F); F = F.loc[T_.index]; F["T"] = T_; F["S"] = S_
    F["mdd10"] = fwd_min(F.c, 10); F["fwd"] = F.c.shift(-10) / F.c - 1
    r = F.iloc[-1]; tt, ss = r["T"], r["S"]; hist = F.dropna(subset=["mdd10"])
    if miss: print(" 못 받은 시리즈:", miss, "-> 해당 조건은 판정 불가로 보고 결과를 '부분 판정'으로 표시")
    print(f" 기준일 {F.index[-1].date()} | 전술 국면: {tt} (전일 {F['T'].iloc[-2]}) | 구조 국면: {ss} (전일 {F['S'].iloc[-2]})")
    print(f" 속성: {', '.join(RG.attrs(r)) or '없음'} | 느린 경보: {', '.join(RG.slow_alarms(r)) or '없음'}")
    print(f" 판정 입력: VIX/VIX3M {r.vr:.2f}, 신용(HYG/IEF) 10일 {r.cr10*100:+.2f}%·60일 {r.cr60*100:+.2f}%, USDJPY 5일 {r.jpy5*100:+.2f}%, 10일 수익률 {r.r10*100:+.1f}%, 하루 z {r.z:.2f}, "
          f"200일선 대비 {(r.c/r.ma200-1)*100:+.1f}%, 주봉 RSI {r.wrsi:.0f}, 5년 추세 z {r.trendz:.2f}, 시장 폭 60일 {r.br60*100:+.1f}%, 1년 고점 대비 {r.dd252*100:+.1f}%")
    rk = lambda g: (g.mdd10 <= -0.05).mean()
    base = rk(hist); gt = hist[hist["T"] == tt]; gs = hist[hist["S"] == ss]; g2 = hist[(hist["T"] == tt) & (hist["S"] == ss)]
    ep2 = RG.episodes(g2.index)
    print(f" 위험 확률(2007~): 기저 {base*100:.0f}% | 전술 {tt} {rk(gt)*100:.0f}% ({RG.episodes(gt.index)}국면) | 구조 {ss} {rk(gs)*100:.0f}% ({RG.episodes(gs.index)}국면)"
          + (f" | 둘 다 {rk(g2)*100:.0f}% ({ep2}국면)" if ep2 >= 10 else f" | 둘 다: 독립국면 {ep2}개라 생략"))
    risk_regime = rk(g2) if ep2 >= 10 else rk(gs)
    # 위험 모델 v1: 로지스틱(log VIX, 1년 고점 대비 낙폭). 결과가 확정된 과거 전체(1999~)로 매번 적합.
    # 2020~2026 표본 밖 검증: AUC 0.65, 브라이어 기저 대비 약간 개선이나 통계적으로 확정 안 됨 (국면 모델 AUC 0.59, VIX 단독 0.61) -> 국면보다 이 모델을 위험 출발점으로 씀
    Lg = pd.DataFrame({"c": qf, "vix": vf}); Lg["dd252"] = qf / qf.rolling(252).max() - 1; Lg["mdd10"] = fwd_min(qf, 10)
    Lh = Lg.dropna(); yv = (Lh.mdd10 <= -0.05).values.astype(float)
    Xf = lambda df: np.column_stack([np.ones(len(df)), np.log(df.vix.values), df.dd252.values]); xv = Xf(Lh); wv = np.zeros(3)
    for _ in range(50):
        pv = 1 / (1 + np.exp(-xv @ wv)); wv += np.linalg.solve(xv.T @ (xv * (pv * (1 - pv))[:, None]) + 1e-6 * np.eye(3), xv.T @ (yv - pv))
    xn = Lg.iloc[[-1]]; risk_model = float(1 / (1 + np.exp(-Xf(xn) @ wv))[0]); base = float(yv.mean())
    print(f" 위험 모델(로지스틱 VIX {xn.vix.iloc[0]:.1f} + 1년 고점 대비 {xn.dd252.iloc[0]*100:.1f}%, 1999~ 적합): {risk_model*100:.0f}% | 평소(1999~) {base*100:.0f}% | 국면 기준값 {risk_regime*100:.0f}% (참고)")
    print("  참고: 위험 구분력은 보통 수준(표본 밖 AUC 0.65, 0.5=무작위). 기저 대비 개선은 통계적으로 확정 안 됨(약한 신호). 정확한 확률은 시기마다 흔들림(2007~2019 발생률 12%, 2020~ 17%)")
    pt = ud(gt)
    print(f" 방향(참고): 전술 {tt} 조건부 {fmt(pt)} (표본 밖에서 기저율 못 이김)")
    sig = r.vix / 100 * np.sqrt(10 / 252)
    print(f" 예상 10일 변동폭(VIX 기준 1σ): ±{sig*100:.1f}% | 레버리지 소멸 추정(10일, 같은 변동성 지속 가정): QLD 약 -{0.5*2*sig**2*100:.2f}%, TQQQ 약 -{0.5*6*sig**2*100:.2f}%")
    DEEP += RG.mode_flags(F)  # 켜지는 날만: |z|≥2.5, T1, VIX 25/30/40 상향 돌파, 새 느린 경보, 3일 유지된 국면 전환 (2007~ 약 19%의 날)
    act = "레버리지 축소 검토" if risk_model >= 0.30 else ("유지·신규 자금은 분할" if risk_model >= 0.15 else "정상")
    print(f" 사전 행동 규칙(위험 모델 기준, 검증 중인 가설): 30% 이상 '레버리지 축소 검토' / 15~30% '유지·신규 자금은 분할' / 15% 미만 '정상' -> 오늘: {act}")
    SNAP["국면"] = {"전술": tt, "구조": ss, "속성": RG.attrs(r), "느린경보": RG.slow_alarms(r), "위험_기저": round(base, 3), "위험_모델": round(risk_model, 3), "위험_국면": round(risk_regime, 3),
                  "위험_전술": round(rk(gt), 3), "위험_구조": round(rk(gs), 3), "방향_전술": [round(v, 3) for v in pt], "행동규칙": act, "변동폭_1σ": round(float(sig), 4),
                  "입력": {k: round(float(r[k]), 4) for k in ["vr", "cr10", "cr60", "jpy5", "jpy20", "r10", "z", "wrsi", "trendz", "br60", "dd252", "sox20", "vix"]}}
except Exception as e:
    print(" 국면 판정 실패:", type(e).__name__, e, "-> 브리프에 '국면 판정 실패' 표시, 위험은 기저율로")
    DEEP.append("국면 판정 실패")
print(f" => 모드: {'깊은 모드 (' + '; '.join(DEEP) + ')' if DEEP else '짧은 모드 (평온)'}")
SNAP["모드"] = {"깊은": bool(DEEP), "이유": DEEP}

print("\n[채점용 - QQQ 최근 30거래일 종가 (거래일 순번: 날짜 종가)]")
if "QQQ" in D:
    qc = D["QQQ"].close.iloc[-30:]
    print(" " + " | ".join(f"{i}:{d.date()} {v:.2f}" for i, (d, v) in enumerate(qc.items())))


print("\n\n########## BMNR (BitMine, ETH 보유 회사) ##########")
try:
    import numpy as np
    def crypto(sym, url_rng="range=2y"):
        r = j(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{url_rng}&interval=1d")["chart"]["result"][0]
        i = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_localize(None).normalize()  # 암호화폐는 UTC 날짜 기준 (종가 = UTC 자정 = ET 19시)
        s = pd.Series(r["indicators"]["quote"][0]["close"], index=i).dropna(); s = s[~s.index.duplicated(keep="last")]
        if s.index[-1] >= pd.Timestamp.now(tz="UTC").tz_localize(None).normalize(): s = s.iloc[:-1]  # 아직 끝나지 않은 UTC 당일봉 제외
        return s
    b = yahoo("BMNR", "2y"); ec = crypto("ETH-USD"); btc = crypto("BTC-USD", "range=1mo")
    try:
        t = dt.date.today(); f = t - dt.timedelta(days=14)
        rows = j(f"https://api.nasdaq.com/api/quote/BMNR/historical?assetclass=stocks&fromdate={f}&limit=15&todate={t}")["data"]["tradesTable"]["rows"]
        nb = {pd.to_datetime(r["date"]).normalize(): float(r["close"].replace("$", "").replace(",", "")) for r in rows}
    except Exception: nb = None
    c = b.close; last = c.index[-1]; p = c.iloc[-1]; p_b = p
    b_vol = c.pct_change().iloc[-60:].std() * np.sqrt(252); b_band = 0.5 * b_vol * np.sqrt(10 / 252)
    if not nb: chk = "백업 없음(Nasdaq 실패)"
    elif last not in nb: chk = "날짜 불일치"
    else:
        df_ = abs(nb[last]/p-1)*100; chk = f"OK(차이 {df_:.2f}%)" if df_ <= 0.5 else f"불일치({df_:.2f}%) - 판정 보류"
    rt = lambda s, n: (s.iloc[-1]/s.iloc[-1-n]-1)*100 if len(s) > n else float("nan")
    ytd = (p/c[c.index < dt.datetime(last.year, 1, 1)].iloc[-1]-1)*100 if (c.index < dt.datetime(last.year, 1, 1)).any() else float("nan")
    prior = b.iloc[-21:-1]; r6 = b.iloc[-127:-1]
    ma50 = c.rolling(50).mean().iloc[-1]; ma200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else float("nan")
    volx = b.volume.iloc[-1]/b.volume.iloc[-21:-1].mean()
    rng = b.high.iloc[-1]-b.low.iloc[-1]; wick = (min(b.open.iloc[-1], p)-b.low.iloc[-1])/rng if rng > 0 else 0
    print(f"[BMNR] 종가 {p:.2f} ({c.pct_change().iloc[-1]*100:+.2f}%) 기준 {last.date()} 정규장 종가 | 교차검증 {chk}")
    print(f" 수익률 5일 {rt(c,5):+.1f}% / 1M {rt(c,21):+.1f}% / 3M {rt(c,63):+.1f}% / 6M {rt(c,126):+.1f}% / YTD {ytd:+.1f}%")
    print(f" MA50 {ma50:.2f}({'위' if p>ma50 else '아래'}) / MA200 {ma200:.2f}({'위' if p>ma200 else '아래'}) | RSI 일 {rsi(c).iloc[-1]:.1f} / 주 {rsi(c.resample('W-FRI').last().dropna()).iloc[-1]:.1f}")
    print(f" 거래량 20일평균 대비 {volx:.2f}x | 아래꼬리 {wick:.2f} | 지지: 직전20일 저점 {prior.low.min():.2f}, 6M 저점 {r6.low.min():.2f} (당일 저점 {b.low.iloc[-1]:.2f}) | 저항: 20일고점 {prior.high.max():.2f}, 6M고점 {r6.high.max():.2f}")
    rb = {"low": b.low.iloc[-1], "p": p, "prev": c.iloc[-2], "sup20": prior.low.min(), "volx": volx, "rd": rsi(c).iloc[-1], "wick": wick, "chk": chk,
          "res": (sorted(x for x in [ma50, ma200, prior.high.max(), r6.high.max()] if x == x and x > p) or [None])[0]}
    print(" 규칙 판정:", verdict(rb))
    print(f"[ETH-USD] {ec.iloc[-1]:.2f} ({ec.pct_change().iloc[-1]*100:+.2f}%, 7일 {rt(ec,7):+.1f}%, 30일 {rt(ec,30):+.1f}%) 기준 {ec.index[-1].date()} (UTC 일봉) | MA200 {ec.rolling(200).mean().iloc[-1]:.0f} | RSI {rsi(ec).iloc[-1]:.1f}")
    print(f"[BTC-USD] {btc.iloc[-1]:.0f} ({btc.pct_change().iloc[-1]*100:+.2f}%, 7일 {rt(btc,7):+.1f}%) 기준 {btc.index[-1].date()} (UTC 일봉)")
    e_on_b = ec.reindex(c.index).ffill()  # BMNR 거래일 기준으로 ETH를 맞춤 (월요일 = 금->월 변화)
    j2 = pd.DataFrame({"b": c.pct_change(), "e": e_on_b.pct_change()}).dropna().iloc[-60:]
    beta = j2.cov().iloc[0, 1]/j2.e.var(); corr = j2.corr().iloc[0, 1]
    print(f" BMNR vs ETH 최근 60거래일: 베타 {beta:.2f} (ETH 1% 움직일 때 BMNR 평균 {beta:.2f}%), 상관 {corr:.2f}")
    print(f" 상대 성과 20거래일: BMNR {rt(c,20):+.1f}% vs ETH {rt(e_on_b,20):+.1f}% (BMNR이 더 약하면 mNAV 프리미엄 축소 가능성 - 확인 필요)")
    print(f" BMNR 60일 실현변동성 연 {b_vol*100:.0f}% -> 10거래일 보합 범위 ±{b_band*100:.1f}% (±0.5σ)")
    # ETH 과거 유사국면 (BMNR 이력이 짧아 ETH로 대신), 14일 뒤(=약 10거래일), 보합 = ±0.5σ(ETH 60일 실현변동성 기준)
    ef = crypto("ETH-USD", "period1=915148800&period2=4102444800"); a2 = pd.DataFrame({"c": ef}); a2["rsi"] = rsi(ef); a2["ma200"] = ef.rolling(200).mean()
    a2["dd30"] = ef/ef.rolling(30).max()-1; a2["fwd"] = ef.shift(-14)/ef-1; a2["mdd"] = fwd_min(ef, 14)
    a2["band"] = 0.5 * ef.pct_change().rolling(60).std() * np.sqrt(14)
    # BMNR -15% 하락을 BMNR 10일 변동폭의 몇 σ인지로 바꾼 뒤(고유 변동까지 포함), 같은 σ 배수의 ETH 하락을 위험 사건으로 정의
    kk = 0.15 / (b_vol * np.sqrt(10 / 252)); a2["sig14"] = ef.pct_change().rolling(60).std() * np.sqrt(14)
    thr = -kk * a2.sig14.iloc[-1]
    x2 = a2.iloc[-1]; h2 = a2.dropna(subset=["fwd", "ma200", "mdd", "band"])
    bd = lambda v: 0 if v > -0.10 else 1 if v > -0.25 else 2
    b_r2 = lambda v: 0 if v < 30 else 1 if v < 40 else 2 if v < 60 else 3
    cs = [("RSI구간", lambda d: d.rsi.map(b_r2) == b_r2(x2.rsi)), ("200일선 위/아래", lambda d: (d.c < d.ma200) == (x2.c < x2.ma200)),
          ("30일고점 대비 낙폭", lambda d: d.dd30.map(bd) == bd(x2.dd30))]
    print(f"\n[ETH 과거 유사국면 - BMNR 대용, ETH-USD {h2.index[0].year}~, 14일 뒤, 보합 ±0.5σ | 위험 = 14일 안 ETH 최저가가 -{kk:.2f}σ 이하 (BMNR -15% = 자기 10일 변동폭의 {kk:.2f}σ, 오늘 ETH 기준 {thr*100:.1f}%)]")
    print(f" 현재 ETH: RSI {x2.rsi:.1f}, 200일선 {'아래' if x2.c < x2.ma200 else '위'}, 30일고점 대비 {x2.dd30*100:.1f}%, 보합 범위 ±{x2.band*100:.1f}%")
    h2 = h2.dropna(subset=['sig14']); ev = lambda s: (s.mdd <= -kk * s.sig14).mean()
    pe = ud(h2); re_ = ev(h2)
    print(f" ETH 기저율: {fmt(pe)} | 위험 {re_*100:.0f}%")
    best2 = None
    for k in range(len(cs), 0, -1):
        m = np.ones(len(h2), bool)
        for _, f_ in cs[:k]: m &= f_(h2).values
        s = h2[m]
        if len(s) == 0: continue
        ep = int((s.index.to_series().diff().dt.days > 20).sum()+1); p = ud(s); rk2 = ev(s)
        print(f" 조건 {k}개({', '.join(n for n, _ in cs[:k])}): 표본 {len(s)}일/독립국면 {ep}개 | {fmt(p)} | 위험 {rk2*100:.0f}% | 중앙값 {s.fwd.median()*100:+.1f}%")
        if best2 is None and ep >= 10: best2 = (k, ep, p, rk2)
    print(f" => ETH 대표값: {fmt(best2[2])} | 위험 {best2[3]*100:.0f}% (조건 {best2[0]}개, 국면 {best2[1]}개)" if best2 else " => 독립국면 10개 이상 없음: 확률 신뢰 낮음")
    print(f" 참고: 최근 60거래일 BMNR은 ETH 움직임의 약 {beta:.1f}배로 움직임. ETH 확률은 방향만 대신하는 것이고 mNAV·희석 요인은 반영 안 됨")
    rb_show = best2[3] if best2 else re_
    act_b = "비중 축소 검토" if rb_show >= 0.40 else ("유지" if rb_show >= 0.20 else "정상")
    print(f" BMNR 사전 행동 규칙(위험 표시값 {rb_show*100:.0f}% 기준, 검증 중인 가설): 40% 이상 '비중 축소 검토' / 20~40% '유지' / 20% 미만 '정상' -> 오늘: {act_b}")
    SNAP["BMNR"] = {"종가": round(float(p_b), 4), "ETH": round(float(ec.iloc[-1]), 2), "베타": round(float(beta), 3), "상관": round(float(corr), 3), "보합범위": round(float(b_band), 4),
                    "ETH기저": {"확률": [round(v, 3) for v in pe], "위험": round(re_, 3)}, "규칙판정": verdict(rb), "위험_표시": round(rb_show, 3), "행동규칙": act_b,
                    "ETH유사국면": ({"조건수": best2[0], "국면수": best2[1], "확률": [round(v, 3) for v in best2[2]], "위험": round(best2[3], 3)} if best2 else None)}
    bc = c.iloc[-30:]
    print("\n[채점용 - BMNR 최근 30거래일 종가]\n " + " | ".join(f"{i}:{d.date()} {v:.2f}" for i, (d, v) in enumerate(bc.items())))
except Exception as ex:
    print(" BMNR 섹션 실패:", type(ex).__name__, ex)

print("\n\n########## 추가 계산 (brief-v2.1) ##########")
import numpy as np
NOW_ET = pd.Timestamp.now(tz="America/New_York")

# 1) 시간외 가격: 브리프 실행 시각의 마지막 체결(프리마켓/애프터마켓 포함)
def last_trade(sym):
    r = j(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=5m&includePrePost=true")["chart"]["result"][0]
    i = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    s = pd.Series(r["indicators"]["quote"][0]["close"], index=i).dropna()
    return float(s.iloc[-1]), s.index[-1]
print(f"\n[시간외 가격 - 실행 시각 {NOW_ET:%Y-%m-%d %H:%M} ET, Yahoo 5분봉 프리/애프터 포함]")
SNAP["시간외"] = {}
for sym, ref in (("QQQ", R.get("QQQ", {}).get("p")), ("BMNR", globals().get("p_b")), ("ETH-USD", None)):
    try:
        px, ts = last_trade(sym)
        if ref:
            print(f" {sym} {px:.2f} ({ts:%m-%d %H:%M} ET 체결) | 직전 정규장 종가 {ref:.2f} 대비 {(px/ref-1)*100:+.2f}%")
            SNAP["시간외"][sym] = {"가격": round(px, 4), "시각": f"{ts:%Y-%m-%d %H:%M}", "종가대비": round((px/ref-1)*100, 2)}
        else:
            print(f" {sym} {px:.2f} ({ts:%m-%d %H:%M} ET)"); SNAP["시간외"][sym] = {"가격": round(px, 2), "시각": f"{ts:%Y-%m-%d %H:%M}"}
    except Exception as e:
        print(f" {sym}: 못 구함 ({type(e).__name__})")

# 2) BMNR 움직임 분해: ETH는 BMNR 종가와 같은 시각(16:00 ET)으로 맞춤
#    log(1+BMNR) = log(1+ETH) + 나머지  (나머지 = 할인/프리미엄 변화 + 주당 ETH 변화. 하루짜리는 거의 할인 변화)
try:
    r = j("https://query1.finance.yahoo.com/v8/finance/chart/ETH-USD?range=3mo&interval=1h")["chart"]["result"][0]
    i = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    eh = pd.Series(r["indicators"]["quote"][0]["close"], index=i).dropna()
    bcl = b.close.iloc[-30:]
    e16 = pd.Series({d: eh[eh.index <= pd.Timestamp(d).tz_localize("America/New_York") + pd.Timedelta(hours=15)].iloc[-1] for d in bcl.index})
    print(f"\n[BMNR 움직임 분해 - ETH = 같은 날 16:00 ET 가격 (1시간봉 15:00~16:00 종가) | 나머지 = 할인 변화 + 주당 ETH 변화]")
    print(f" ETH 16:00 ET ({bcl.index[-1].date()}): {e16.iloc[-1]:,.2f}  (참고: 시트 'ETH 가격' 칸은 UTC 일봉 종가 = 19:00 ET)")
    SNAP["BMNR분해"] = {"ETH_16ET": round(float(e16.iloc[-1]), 2)}
    for n, lab in ((1, "1일"), (5, "5거래일"), (21, "1개월")):
        lb = np.log(bcl.iloc[-1]/bcl.iloc[-1-n]); le = np.log(e16.iloc[-1]/e16.iloc[-1-n]); rest = lb - le
        pc = lambda x: (np.exp(x)-1)*100
        print(f" {lab}: BMNR {pc(lb):+.1f}% = ETH {pc(le):+.1f}% 몫 + 나머지 {pc(rest):+.1f}% ({'할인 축소/주당 ETH 증가 쪽' if rest > 0 else '할인 확대/희석 쪽'})")
        SNAP["BMNR분해"][lab] = {"BMNR": round(pc(lb), 2), "ETH": round(pc(le), 2), "나머지": round(pc(rest), 2)}
except Exception as e:
    print(" BMNR 분해 실패:", type(e).__name__, e)

# 3) 가속도 상태(1차·2차 도함수) + 그 상태 뒤 역사적 위험 — 2026-11-24 검증: 위험 모델에 더하는 예측력 없음. 오독 방지·기록용
def accel_state(s, k):
    roc = s.pct_change(k); acc = roc.diff()
    st = np.select([(roc > 0) & (acc > 0), (roc > 0) & (acc <= 0), (roc <= 0) & (acc > 0), (roc <= 0) & (acc <= 0)],
                   ["상승·가속", "상승·감속", "하락·감속", "하락·가속"], default="")
    return pd.Series(st, index=s.index).where(acc.notna()), roc, acc
try:
    qd = RG.yfull("QQQ").dropna()
    qw = qd.resample("W-FRI").last().dropna(); qw = qw[qw.index <= qd.index[-1]]  # 끝나지 않은 주 제외
    SNAP["가속도"] = {}
    print("\n[가속도 상태 - 1차 = ROC(속도), 2차 = ROC의 직전 대비 변화(가속) | 2026-11-24 검증: 위험 모델에 더하는 예측력 없음, 오독 방지·기록용]")
    for nm, s, k, Hn, thr, unit in (("일봉", qd, 20, 10, -0.05, "10거래일"), ("주봉", qw, 4, 4, -0.07, "4주")):
        st, roc, acc = accel_state(s, k)
        fmin = pd.concat([s.shift(-i) for i in range(1, Hn+1)], axis=1).min(axis=1)/s - 1
        ev = (fmin <= thr).where(s.shift(-Hn).notna())
        h = pd.DataFrame({"st": st, "ev": ev}).dropna()
        cur = st.iloc[-1]; sub = h[h.st == cur]
        print(f" {nm}: {k}{'일' if nm=='일봉' else '주'} ROC {roc.iloc[-1]*100:+.2f}% (직전 {roc.iloc[-2]*100:+.2f}%, 변화 {acc.iloc[-1]*100:+.2f}%p) -> {cur} "
              f"| 이 상태 뒤 {unit} 안 {thr:.0%} 위험 {sub.ev.mean()*100:.0f}% (평소 {h.ev.mean()*100:.0f}%, 독립 약 {len(sub)//Hn}개, {s.index[0].year}~)")
        SNAP["가속도"][nm] = {"ROC": round(float(roc.iloc[-1])*100, 2), "변화pp": round(float(acc.iloc[-1])*100, 2), "상태": cur,
                            "상태위험": round(float(sub.ev.mean()), 3), "평소위험": round(float(h.ev.mean()), 3)}
except Exception as e:
    print(" 가속도 계산 실패:", type(e).__name__, e)

print("\nSNAPSHOT_JSON: " + json.dumps(SNAP, ensure_ascii=False, default=lambda o: round(float(o), 4) if isinstance(o, (np.floating, np.integer)) else str(o)))
