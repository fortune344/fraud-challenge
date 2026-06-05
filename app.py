# -*- coding: utf-8 -*-
"""
ANTI-FRAUDE — Hackathon IT 2026 · Lomé Business School

Interface NÉO-BRUTALISTE : fond crème texturé, bordures noires, ombres dures,
typographie géante, accent jaune acide. Volontairement aux antipodes du
« dashboard sombre » générique.

Fonctionnalités : scoring (detect_fraud), profils comportementaux, détection
de réseaux de fraude (graphe), prédiction de propension par client, et
génération d'un rapport téléchargeable.

Lancement :  streamlit run app.py
"""

import csv
import io
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from fraud_detection import (_clean_row, build_user_profiles,
                             detect_fraud, detect_fraud_networks,
                             forecast_client_risk)


# --------------------------------------------------------------------------- #
#  Palette néo-brutaliste                                                       #
# --------------------------------------------------------------------------- #
INK = "#111111"
ACID = "#D9FF00"
CRIT_C = "#FF2E2E"
HIGH_C = "#FF8A00"
MED_C = "#FFD400"
LOW_C = "#00C46A"

RISK_ORDER = ["Critique", "Élevé", "Moyen", "Faible"]
RISK_COLOR = {"Critique": CRIT_C, "Élevé": HIGH_C, "Moyen": MED_C, "Faible": LOW_C}
CHIP_TXT = {CRIT_C: "#fff", HIGH_C: "#fff", MED_C: INK, LOW_C: INK}
PROP_COLOR = {"Forte": CRIT_C, "Modérée": HIGH_C, "Faible": LOW_C}

# Jeu d'exemple : les 10 transactions officielles + un anneau de fraude
# (commerçant compromis « GhostPay » touchant 3 comptes) pour la démo réseau.
_EXEMPLE_CSV = """transaction_id,timestamp,user_id,amount,currency,merchant,country,card_present
T-001,2025-05-02T09:15:00Z,U1,48.00,EUR,Boulangerie,FR,true
T-002,2025-05-09T12:40:00Z,U1,52.50,EUR,Supermarche,FR,true
T-003,2025-05-15T19:05:00Z,U1,47.20,EUR,Restaurant,FR,true
T-004,2025-06-01T03:22:00Z,U1,4800.00,EUR,Bijouterie,FR,false
T-010,2025-06-01T10:00:00Z,U2,60.00,EUR,Cafe,FR,true
T-011,2025-06-01T10:40:00Z,U2,75.00,JPY,Konbini,JP,false
T-020,2025-06-02T14:00:00Z,U3,-30.00,EUR,Remboursement?,FR,true
T-021,2025-06-02T15:00:00Z,U3,40.00,EUR,Kiosque,,true
T-030,2025-06-03T08:00:00Z,U4,90.00,EUR,Hotel,FR,true
T-031,2025-06-06T08:00:00Z,U4,120.00,USD,Hotel,US,false
T-040,2025-06-04T02:10:00Z,U5,0.00,EUR,GhostPay,FR,false
T-041,2025-06-04T02:30:00Z,U6,-15.00,EUR,GhostPay,FR,false
T-042,2025-06-04T02:45:00Z,U7,500.00,EUR,GhostPay,,false
"""


# --------------------------------------------------------------------------- #
#  Helpers de données                                                          #
# --------------------------------------------------------------------------- #
def _risk_level(score):
    if score >= 0.85:
        return "Critique"
    if score >= 0.70:
        return "Élevé"
    if score >= 0.50:
        return "Moyen"
    return "Faible"


def _risk_color(score):
    return RISK_COLOR[_risk_level(score)]


def _rows_from_csv_text(text):
    reader = csv.DictReader(io.StringIO(text))
    return [_clean_row(row) for row in reader]


def _build_dataframe(transactions, results):
    by_id = {r["transaction_id"]: r for r in results}
    rows = []
    for t in transactions:
        r = by_id.get(t.get("transaction_id"), {})
        score = float(r.get("fraud_score", 0.0))
        rows.append({
            "transaction_id": t.get("transaction_id"),
            "timestamp": t.get("timestamp"),
            "user_id": t.get("user_id"),
            "amount": t.get("amount"),
            "currency": t.get("currency"),
            "merchant": t.get("merchant"),
            "country": t.get("country"),
            "card_present": t.get("card_present"),
            "fraud_score": round(score, 3),
            "risk": _risk_level(score),
            "is_suspicious": bool(r.get("is_suspicious", False)),
            "reason": r.get("reason", ""),
        })
    return pd.DataFrame(rows)


def _fmt(n):
    try:
        return f"{n:,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _enriched_explanation(row, profile):
    reason = row["reason"] or ""
    amount = row["amount"]
    cur = row["currency"] or ""
    parts = []
    if "très supérieur" in reason and profile and profile.get("median_amount"):
        med = profile["median_amount"]
        if med and isinstance(amount, (int, float)):
            parts.append(f"montant {amount / med:.0f}× supérieur à l'habitude "
                         f"(~{_fmt(med)} {cur})")
    if "Deux pays" in reason:
        parts.append("déplacement géographiquement impossible dans le temps écoulé")
    if "nul ou négatif" in reason:
        parts.append("montant invalide (≤ 0)")
    if "manquants" in reason:
        champ = reason.split(":", 1)[1].strip() if ":" in reason else "information"
        parts.append(f"{champ} absent(e)")
    if "Fréquence" in reason:
        parts.append("rafale de transactions en très peu de temps")
    if "double" in reason:
        parts.append("débit identique répété")
    if profile and row["country"] and profile.get("countries"):
        seen = profile["countries"].get(row["country"], 0)
        if seen <= 1 and len(profile["countries"]) > 1 and row["is_suspicious"]:
            parts.append(f"pays « {row['country']} » inhabituel pour ce client")
    if not parts:
        return reason
    return f"{reason} — " + ", ".join(parts) + "."


# --------------------------------------------------------------------------- #
#  Style néo-brutaliste                                                         #
# --------------------------------------------------------------------------- #
_NOISE = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
          "width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence "
          "type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E"
          "%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E")

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap');

  .stApp { background-color:#F4F1E8; background-image:url("%NOISE%"); }
  .block-container { padding-top:1.4rem; max-width:1200px;
                     font-family:'Space Grotesk',sans-serif; }
  #MainMenu, footer, header { visibility:hidden; }

  @keyframes nbIn { 0%{opacity:0; transform:translateY(-16px) rotate(-2.2deg)}
                    100%{opacity:1; transform:translateY(0) rotate(var(--rot,0deg))} }

  /* Ticker */
  .nb-ticker { background:#111; border:3px solid #111; overflow:hidden;
               white-space:nowrap; margin-bottom:20px; }
  .nb-ticker-track { display:inline-block; padding:8px 0; animation:nb-scroll 24s linear infinite;
                     font-family:'Space Mono',monospace; font-weight:700; font-size:13px;
                     letter-spacing:1px; color:#D9FF00; text-transform:uppercase; }
  @keyframes nb-scroll { from{transform:translateX(0)} to{transform:translateX(-50%)} }

  /* Hero */
  .nb-hero { display:flex; justify-content:space-between; align-items:flex-end;
             gap:18px; margin-bottom:26px; flex-wrap:wrap; position:relative; }
  .nb-title { font-family:'Archivo Black',sans-serif; font-size:74px; line-height:.88;
              letter-spacing:-2px; color:#111; text-transform:uppercase; margin:0; }
  .nb-title .hl { background:#D9FF00; padding:0 8px; box-decoration-break:clone; }
  .nb-sub { font-weight:700; text-transform:uppercase; letter-spacing:2px;
            font-size:13px; color:#111; margin-top:12px; opacity:.7; }
  .nb-right { display:flex; align-items:center; gap:16px; }
  .nb-stamp { font-family:'Archivo Black',sans-serif; text-transform:uppercase;
              font-size:18px; letter-spacing:1px; padding:8px 14px; border:4px solid;
              transform:rotate(-8deg); opacity:.92; line-height:1; text-align:center; }
  .nb-menace { background:#FF2E2E; color:#fff; border:3px solid #111;
               box-shadow:7px 7px 0 #111; padding:14px 22px; text-align:center;
               animation:nbIn .5s cubic-bezier(.2,.8,.2,1.2) .1s both; --rot:2deg; }
  .nb-menace .n { font-family:'Archivo Black'; font-size:54px; line-height:.9; }
  .nb-menace .t { font-weight:700; text-transform:uppercase; letter-spacing:2px;
                  font-size:12px; margin-top:2px; }

  /* KPI */
  .nb-kpi { background:#fff; border:3px solid #111; box-shadow:6px 6px 0 #111;
            padding:16px 18px; height:100%;
            animation:nbIn .5s cubic-bezier(.2,.8,.2,1.2) both; }
  .nb-kpi.acid { background:#D9FF00; }
  .nb-kpi.dark { background:#111; }
  .nb-kpi .lbl { font-weight:700; text-transform:uppercase; letter-spacing:1.5px;
                 font-size:11px; color:#111; }
  .nb-kpi.dark .lbl { color:#D9FF00; }
  .nb-kpi .val { font-family:'Space Mono',monospace; font-weight:700; font-size:38px;
                 color:#111; line-height:1.1; margin-top:2px; }
  .nb-kpi.dark .val { color:#fff; }

  /* Sections */
  .nb-sec { font-family:'Archivo Black',sans-serif; text-transform:uppercase;
            font-size:22px; letter-spacing:-.5px; color:#111; margin:32px 0 14px;
            display:flex; align-items:center; gap:10px; }
  .nb-sec::before { content:""; width:18px; height:18px; background:#D9FF00;
                    border:3px solid #111; display:inline-block; }

  .nb-card { background:#fff; border:3px solid #111; box-shadow:6px 6px 0 #111;
             animation:nbIn .5s cubic-bezier(.2,.8,.2,1.2) .15s both; }
  .nb-row { display:flex; align-items:center; gap:14px; padding:13px 16px;
            border-bottom:3px solid #111; transition:transform .08s, background .15s, box-shadow .15s; }
  .nb-row:last-child { border-bottom:none; }
  .nb-row:hover { background:#FCFBE9; transform:translateX(6px);
                  box-shadow:inset 6px 0 0 #D9FF00; }
  .nb-chip { border:2px solid #111; box-shadow:2px 2px 0 #111; padding:3px 9px;
             font-weight:700; text-transform:uppercase; font-size:11px;
             letter-spacing:.5px; min-width:78px; text-align:center; }
  .nb-id { font-family:'Space Mono',monospace; font-weight:700; font-size:14px; width:70px; }
  .nb-mer { font-weight:700; width:140px; overflow:hidden; white-space:nowrap;
            text-overflow:ellipsis; }
  .nb-reason { flex:1; text-transform:uppercase; font-size:12.5px; font-weight:600;
               letter-spacing:.3px; opacity:.85; }
  .nb-score { font-family:'Space Mono',monospace; font-weight:700; font-size:20px;
              width:64px; text-align:right; }

  .nb-exp { padding:13px 16px; border-bottom:3px solid #111; }
  .nb-exp:last-child { border-bottom:none; }
  .nb-exp .h { font-family:'Space Mono',monospace; font-weight:700; font-size:12px;
               text-transform:uppercase; letter-spacing:.5px; }
  .nb-exp .b { font-weight:500; font-size:14px; margin-top:3px; }

  /* Prédiction */
  .nb-pred { padding:14px 16px; border-bottom:3px solid #111; }
  .nb-pred:last-child { border-bottom:none; }
  .nb-pred-top { display:flex; align-items:center; gap:12px; }
  .nb-pbar { height:14px; background:#F0EDE2; border:2px solid #111; margin-top:8px; }
  .nb-pbar > div { height:100%; }
  .nb-drv { font-family:'Space Mono',monospace; font-size:11px; text-transform:uppercase;
            letter-spacing:.5px; margin-top:6px; opacity:.7; }

  /* Widgets */
  .stButton>button, .stDownloadButton>button {
    background:#D9FF00 !important; color:#111 !important; border:3px solid #111 !important;
    border-radius:2px !important; box-shadow:4px 4px 0 #111 !important; font-weight:700 !important;
    text-transform:uppercase !important; letter-spacing:.5px !important;
    font-family:'Space Grotesk',sans-serif !important; }
  .stButton>button:hover, .stDownloadButton>button:hover {
    transform:translate(-2px,-2px); box-shadow:6px 6px 0 #111 !important; }
  .stButton>button:active, .stDownloadButton>button:active {
    transform:translate(2px,2px); box-shadow:2px 2px 0 #111 !important; }
  [data-baseweb="tag"] { background:#111 !important; border-radius:2px !important;
                         border:2px solid #111 !important; }
  section[data-testid="stSidebar"] { background:#fff; border-right:3px solid #111; }
  .stExpander { border:3px solid #111 !important; border-radius:2px !important;
                box-shadow:5px 5px 0 #111 !important; background:#fff !important; }
  .stExpander summary { font-weight:700 !important; text-transform:uppercase !important;
                        letter-spacing:.5px !important; }
  .nb-foot { font-family:'Space Mono',monospace; font-size:12px; text-transform:uppercase;
             letter-spacing:1px; margin-top:30px; border-top:3px solid #111; padding-top:12px; }
</style>
""".replace("%NOISE%", _NOISE)


def _countup_css(items):
    """Génère le CSS de compteurs animés (0 -> valeur) via @property."""
    css = []
    for key, target in items:
        css.append(f"@property --{key}{{syntax:'<integer>';initial-value:0;inherits:false}}")
        css.append(f".cu-{key}::after{{content:counter({key})}}")
        css.append(f".cu-{key}{{counter-reset:{key} var(--{key});"
                   f"animation:k{key} 1.6s cubic-bezier(.2,.7,.2,1) forwards}}")
        css.append(f"@keyframes k{key}{{to{{--{key}:{int(target)}}}}}")
    return "<style>" + "".join(css) + "</style>"


def _nb_chart(chart):
    return (chart
            .configure_view(strokeWidth=0, fill="transparent")
            .configure(background="transparent")
            .configure_axis(labelColor=INK, titleColor=INK, labelFontWeight=700,
                            labelFont="Space Grotesk", gridColor="rgba(0,0,0,.08)",
                            domainColor=INK, domainWidth=2, tickColor=INK, tickWidth=2)
            .configure_legend(labelColor=INK, titleColor=INK, labelFontWeight=700))


# --------------------------------------------------------------------------- #
#  Composants HTML                                                             #
# --------------------------------------------------------------------------- #
def _kpi(label, value_html, variant="", delay=0.0, rot=0.0):
    return (f'<div class="nb-kpi {variant}" style="animation-delay:{delay}s;--rot:{rot}deg">'
            f'<div class="lbl">{label}</div><div class="val">{value_html}</div></div>')


def _ticker(alerts):
    if not len(alerts):
        return ""
    chunk = "  ◆  ".join(f'{r["transaction_id"]} — {(r["reason"] or "").upper()}'
                         for _, r in alerts.iterrows())
    chunk = "  ◆  " + chunk + "  "
    return (f'<div class="nb-ticker"><div class="nb-ticker-track">'
            f'{chunk}{chunk}</div></div>')


def _risk_rows(view):
    order = view.sort_values("fraud_score", ascending=False)
    out = []
    for _, r in order.iterrows():
        lvl = r["risk"]
        color = RISK_COLOR[lvl]
        out.append(
            f'<div class="nb-row">'
            f'<div class="nb-chip" style="background:{color};color:{CHIP_TXT[color]}">{lvl}</div>'
            f'<div class="nb-id">{r["transaction_id"]}</div>'
            f'<div class="nb-mer">{r["merchant"] or "—"}</div>'
            f'<div class="nb-reason">{(r["reason"] or "").upper()}</div>'
            f'<div class="nb-score">{r["fraud_score"]:.2f}</div></div>')
    return f'<div class="nb-card">{"".join(out)}</div>'


def _network_svg(net):
    """Graphe bipartite clients <-> commerçants ; rouge = suspect, anneaux mis en avant."""
    users = [n for n in net["nodes"] if n["type"] == "user"]
    merch = [n for n in net["nodes"] if n["type"] == "merchant"]
    if not users or not merch:
        return '<div class="nb-card"><div class="nb-row"><div class="nb-reason">' \
               'Pas assez de données pour le graphe.</div></div></div>'

    W, rowH, padY = 640, 36, 34
    H = max(len(users), len(merch)) * rowH + padY
    xu, xm = 130, W - 130

    def ys(items):
        if len(items) == 1:
            return {items[0]["id"]: H / 2}
        step = (H - padY) / (len(items) - 1)
        return {it["id"]: padY / 2 + i * step for i, it in enumerate(items)}

    yu, ym = ys(users), ys(merch)

    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block">']
    # Arêtes
    for e in net["edges"]:
        if e["user"] not in yu or e["merchant"] not in ym:
            continue
        x1, y1, x2, y2 = xu, yu[e["user"]], xm, ym[e["merchant"]]
        if e["flagged"]:
            svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                       f'stroke="{CRIT_C}" stroke-width="3"/>')
        else:
            svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                       f'stroke="#111" stroke-width="1.2" opacity="0.3"/>')
    # Noeuds clients
    for n in users:
        y = yu[n["id"]]
        fill = CRIT_C if n["flagged"] else "#111"
        svg.append(f'<rect x="{xu - 9}" y="{y - 9}" width="18" height="18" '
                   f'fill="{fill}" stroke="#111" stroke-width="2"/>')
        svg.append(f'<text x="{xu - 16}" y="{y + 4}" text-anchor="end" '
                   f'font-family="Space Mono" font-weight="700" font-size="13" '
                   f'fill="#111">{n["id"]}</text>')
    # Noeuds commerçants
    for n in merch:
        y = ym[n["id"]]
        ring = n.get("ring")
        fill = CRIT_C if ring else (HIGH_C if n["flagged"] else "#fff")
        sw = 3 if ring else 2
        svg.append(f'<rect x="{xm - 9}" y="{y - 9}" width="18" height="18" '
                   f'fill="{fill}" stroke="#111" stroke-width="{sw}"/>')
        label = (n["id"][:16])
        weight = "700" if ring else "600"
        svg.append(f'<text x="{xm + 16}" y="{y + 4}" text-anchor="start" '
                   f'font-family="Space Grotesk" font-weight="{weight}" font-size="13" '
                   f'fill="#111">{label}{" ⚠" if ring else ""}</text>')
    svg.append("</svg>")
    return f'<div class="nb-card" style="padding:14px 16px">{"".join(svg)}</div>'


def _forecast_rows(forecast):
    out = []
    for uid in sorted(forecast, key=lambda u: forecast[u]["score"], reverse=True):
        f = forecast[uid]
        color = PROP_COLOR[f["level"]]
        pct = int(round(f["score"] * 100))
        drivers = ", ".join(f'{name} ({int(c*100)})' for name, c in f["drivers"][:3]) or "—"
        out.append(
            f'<div class="nb-pred"><div class="nb-pred-top">'
            f'<div class="nb-chip" style="background:{color};color:{CHIP_TXT[color]}">{f["level"]}</div>'
            f'<div class="nb-id">{uid}</div>'
            f'<div style="flex:1;font-weight:700;text-transform:uppercase;font-size:12.5px">'
            f'Propension de fraude</div>'
            f'<div class="nb-score">{pct}%</div></div>'
            f'<div class="nb-pbar"><div style="width:{pct}%;background:{color}"></div></div>'
            f'<div class="nb-drv">Facteurs : {drivers}</div></div>')
    return f'<div class="nb-card">{"".join(out)}</div>'


# --------------------------------------------------------------------------- #
#  Rapport                                                                     #
# --------------------------------------------------------------------------- #
def _build_report_md(df, alerts, net, forecast, profiles, currency_ref):
    total = len(df)
    flagged = len(alerts)
    taux = (flagged / total * 100) if total else 0
    montant = df.loc[df["is_suspicious"] & (df["amount"] > 0), "amount"].sum()
    L = []
    L.append("# RAPPORT ANTI-FRAUDE")
    L.append(f"_Généré le {date.today().isoformat()} · Hackathon IT 2026 — LBS_\n")
    L.append("## 1. Synthèse")
    L.append(f"- Transactions analysées : **{total}**")
    L.append(f"- Transactions suspectes : **{flagged}** (taux {taux:.0f} %)")
    L.append(f"- Montant sous surveillance : **{_fmt(montant)} {currency_ref}**")
    L.append(f"- Réseaux de fraude détectés : **{len(net['rings'])}**\n")
    L.append("## 2. Alertes détaillées")
    if flagged:
        for _, r in alerts.iterrows():
            L.append(f"- **{r['transaction_id']}** ({r['user_id']}) · {r['risk']} · "
                     f"score {r['fraud_score']:.2f} — {_enriched_explanation(r, profiles.get(r['user_id']))}")
    else:
        L.append("- Aucune alerte.")
    L.append("\n## 3. Réseaux de fraude")
    if net["rings"]:
        for ring in net["rings"]:
            L.append(f"- Commerçant compromis **{ring['merchant']}** — {ring['n_users']} "
                     f"comptes liés : {', '.join(ring['users'])}")
    else:
        L.append("- Aucun anneau détecté sur ce lot.")
    L.append("\n## 4. Prédiction — propension de fraude par client")
    for uid in sorted(forecast, key=lambda u: forecast[u]["score"], reverse=True):
        f = forecast[uid]
        drv = ", ".join(name for name, _ in f["drivers"][:3]) or "—"
        L.append(f"- **{uid}** : propension {f['level']} ({int(f['score']*100)} %) — facteurs : {drv}")
    L.append("\n## 5. Recommandations")
    if net["rings"]:
        L.append("- Bloquer et enquêter en priorité sur les commerçants compromis identifiés.")
    if taux >= 30:
        L.append("- Taux d'alertes élevé : renforcer les contrôles (authentification forte).")
    forts = [u for u in forecast if forecast[u]["level"] == "Forte"]
    if forts:
        L.append(f"- Surveiller de près les clients à propension Forte : {', '.join(sorted(forts))}.")
    L.append("- Confirmer les transactions critiques auprès des clients avant validation.")
    return "\n".join(L)


def _build_report_html(md):
    body = []
    for line in md.split("\n"):
        if line.startswith("# "):
            body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            body.append(f"<li>{line[2:]}</li>")
        elif line.startswith("_") and line.endswith("_"):
            body.append(f"<p class='meta'>{line[1:-1]}</p>")
        elif line.strip():
            body.append(f"<p>{line}</p>")
    html = "".join(body).replace("**", "")
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport Anti-Fraude</title><style>
body{{font-family:'Space Grotesk',Arial,sans-serif;background:#F4F1E8;color:#111;
max-width:820px;margin:40px auto;padding:0 24px}}
h1{{font-size:42px;text-transform:uppercase;background:#D9FF00;display:inline-block;
padding:6px 14px;border:4px solid #111;box-shadow:8px 8px 0 #111}}
h2{{font-size:22px;text-transform:uppercase;border-bottom:4px solid #111;
padding-bottom:6px;margin-top:34px}}
li{{margin:6px 0;border-left:4px solid #111;padding-left:10px;list-style:none}}
.meta{{font-family:monospace;text-transform:uppercase;opacity:.7}}
</style></head><body>{html}</body></html>"""


# --------------------------------------------------------------------------- #
#  Interface principale                                                        #
# --------------------------------------------------------------------------- #
def render_interface():
    st.set_page_config(page_title="ANTI-FRAUDE", page_icon="🟡", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### DONNÉES")
        source = st.radio("Source", ("Jeu d'exemple", "Importer un CSV"),
                          label_visibility="collapsed")
        transactions = None
        if source == "Importer un CSV":
            up = st.file_uploader("Fichier CSV", type=["csv"])
            if up is not None:
                try:
                    transactions = _rows_from_csv_text(up.getvalue().decode("utf-8"))
                except Exception:
                    st.error("CSV invalide.")
        else:
            transactions = _rows_from_csv_text(_EXEMPLE_CSV)
        st.caption("Colonnes : transaction_id, timestamp, user_id, amount, "
                   "currency, merchant, country, card_present.")

    if not transactions:
        st.info("⬅️ Importez un CSV ou choisissez le jeu d'exemple.")
        st.stop()

    results = detect_fraud(transactions)
    df = _build_dataframe(transactions, results)
    profiles = build_user_profiles(transactions)
    net = detect_fraud_networks(transactions)
    forecast = forecast_client_risk(transactions)

    with st.sidebar:
        st.markdown("### FILTRES")
        niveaux = st.multiselect("Niveau de risque", RISK_ORDER, default=RISK_ORDER)
        users = sorted(u for u in df["user_id"].dropna().unique())
        users_sel = st.multiselect("Client", users, default=users)
        only_susp = st.toggle("Seulement les suspectes", value=False)

    view = df[df["risk"].isin(niveaux) & df["user_id"].isin(users_sel)]
    if only_susp:
        view = view[view["is_suspicious"]]

    total = len(df)
    flagged = int(df["is_suspicious"].sum())
    taux = (flagged / total * 100) if total else 0.0
    montant_risque = df.loc[df["is_suspicious"] & (df["amount"] > 0), "amount"].sum()
    score_moyen = df["fraud_score"].mean() if total else 0.0
    currency_ref = (df.loc[df["amount"] > 0, "currency"].mode().iloc[0]
                    if (df["amount"] > 0).any() else "EUR")
    alerts = df[df["is_suspicious"]].sort_values("fraud_score", ascending=False)

    # Compteurs animés
    st.markdown(_countup_css([("menace", flagged), ("paie", total),
                              ("taux", round(taux))]), unsafe_allow_html=True)

    # Ticker
    st.markdown(_ticker(alerts), unsafe_allow_html=True)

    # Hero + tampon
    stamp_txt, stamp_col = (("FRAUDE\nDÉTECTÉE", CRIT_C) if flagged
                            else ("AUCUNE\nFRAUDE", LOW_C))
    stamp_html = stamp_txt.replace("\n", "<br>")
    st.markdown(
        f'<div class="nb-hero"><div>'
        f'<div class="nb-title">ANTI-<span class="hl">FRAUDE.</span></div>'
        f'<div class="nb-sub">Détecteur · Profil comportemental · Réseaux · Prédiction · LBS 2026</div>'
        f'</div><div class="nb-right">'
        f'<div class="nb-stamp" style="color:{stamp_col};border-color:{stamp_col}">{stamp_html}</div>'
        f'<div class="nb-menace"><div class="n"><span class="cu-menace"></span></div>'
        f'<div class="t">Menaces actives</div></div></div></div>',
        unsafe_allow_html=True,
    )

    # KPIs (compteurs animés + rotation collage)
    k = st.columns(4, gap="medium")
    k[0].markdown(_kpi("Paiements", '<span class="cu-paie"></span>', "", 0.0, -0.6),
                  unsafe_allow_html=True)
    k[1].markdown(_kpi("Taux de fraude", '<span class="cu-taux"></span>%', "dark", 0.08, 0.7),
                  unsafe_allow_html=True)
    k[2].markdown(_kpi(f"Montant à risque ({currency_ref})", _fmt(montant_risque),
                       "acid", 0.16, -0.5), unsafe_allow_html=True)
    k[3].markdown(_kpi("Score moyen", f"{score_moyen:.2f}", "", 0.24, 0.6),
                  unsafe_allow_html=True)

    # Menaces
    st.markdown('<div class="nb-sec">Menaces détectées</div>', unsafe_allow_html=True)
    if len(view):
        st.markdown(_risk_rows(view), unsafe_allow_html=True)
    else:
        st.markdown('<div class="nb-card"><div class="nb-row"><div class="nb-reason">'
                    'Aucune transaction sur ce filtre.</div></div></div>',
                    unsafe_allow_html=True)

    # Pourquoi ?
    if len(alerts):
        st.markdown('<div class="nb-sec">Pourquoi&nbsp;?</div>', unsafe_allow_html=True)
        items = []
        for _, r in alerts.iterrows():
            color = RISK_COLOR[r["risk"]]
            items.append(
                f'<div class="nb-exp"><div class="h" style="color:{color}">'
                f'▮ {r["transaction_id"]} · {r["user_id"]} · {r["risk"].upper()}</div>'
                f'<div class="b">{_enriched_explanation(r, profiles.get(r["user_id"]))}</div></div>')
        st.markdown(f'<div class="nb-card">{"".join(items)}</div>', unsafe_allow_html=True)

    # Réseaux de fraude
    st.markdown('<div class="nb-sec">Réseaux de fraude</div>', unsafe_allow_html=True)
    if net["rings"]:
        rs = " · ".join(f'{r["merchant"]} ({r["n_users"]} comptes)' for r in net["rings"])
        st.markdown(f'<div class="nb-sub" style="margin:0 0 10px;opacity:1;color:{CRIT_C}">'
                    f'⚠ Anneau(x) détecté(s) : {rs}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="nb-sub" style="margin:0 0 10px">Aucun anneau sur ce lot '
                    '— la détection s\'active dès qu\'un commerçant touche plusieurs comptes.'
                    '</div>', unsafe_allow_html=True)
    st.markdown(_network_svg(net), unsafe_allow_html=True)
    st.caption("■ noir = client · ⬜ commerçant · rouge = impliqué dans une fraude · "
               "⚠ = commerçant compromis (anneau). Trait rouge = lien suspect.")

    # Prédiction
    st.markdown('<div class="nb-sec">Prédiction · propension par client</div>',
                unsafe_allow_html=True)
    st.markdown(_forecast_rows(forecast), unsafe_allow_html=True)
    st.caption("Scorecard explicable (sans étiquettes de fraude) : anticipe quel "
               "client risque de basculer, à partir de son comportement.")

    # Analyse (graphiques)
    st.markdown('<div class="nb-sec">Analyse</div>', unsafe_allow_html=True)
    g1, g2 = st.columns(2, gap="medium")
    with g1:
        st.markdown("**RÉPARTITION DU RISQUE**")
        rep = (df["risk"].value_counts().reindex(RISK_ORDER).fillna(0).reset_index())
        rep.columns = ["Niveau", "Nombre"]
        donut = (alt.Chart(rep).mark_arc(innerRadius=58, stroke=INK, strokeWidth=2.5).encode(
            theta="Nombre:Q",
            color=alt.Color("Niveau:N",
                            scale=alt.Scale(domain=RISK_ORDER,
                                            range=[CRIT_C, HIGH_C, MED_C, LOW_C]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Niveau", "Nombre"]).properties(height=250))
        st.altair_chart(_nb_chart(donut), use_container_width=True)
    with g2:
        st.markdown("**MOTIFS DES ALERTES**")
        if len(alerts):
            motifs = alerts["reason"].value_counts().reset_index()
            motifs.columns = ["Motif", "Nombre"]
            bar = (alt.Chart(motifs).mark_bar(color=ACID, stroke=INK, strokeWidth=2.5).encode(
                x=alt.X("Nombre:Q", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("Motif:N", sort="-x", title=None),
                tooltip=["Motif", "Nombre"]).properties(height=250))
            st.altair_chart(_nb_chart(bar), use_container_width=True)
        else:
            st.success("Aucune alerte.")

    # Rapport
    st.markdown('<div class="nb-sec">Rapport</div>', unsafe_allow_html=True)
    report_md = _build_report_md(df, alerts, net, forecast, profiles, currency_ref)
    report_html = _build_report_html(report_md)
    rc1, rc2 = st.columns(2)
    rc1.download_button("⬇ Rapport (HTML imprimable)", data=report_html.encode("utf-8"),
                        file_name="rapport_antifraude.html", mime="text/html",
                        use_container_width=True)
    rc2.download_button("⬇ Rapport (Markdown)", data=report_md.encode("utf-8"),
                        file_name="rapport_antifraude.md", mime="text/markdown",
                        use_container_width=True)
    with st.expander("APERÇU DU RAPPORT"):
        st.markdown(report_md)

    # Annexes
    with st.expander("PROFILS COMPORTEMENTAUX DES CLIENTS"):
        prof_rows = []
        for uid in sorted(profiles):
            p = profiles[uid]
            prof_rows.append({
                "Client": uid,
                "Transactions": p["n_transactions"],
                "Montant médian": _fmt(p["median_amount"]) if p["median_amount"] else "—",
                "Pays habituel": p["main_country"] or "—",
                "Commerçant habituel": p["main_merchant"] or "—",
                "Pays fréquentés": ", ".join(p["countries"].keys()) or "—",
            })
        st.dataframe(pd.DataFrame(prof_rows), use_container_width=True, hide_index=True)

    with st.expander("TABLE DÉTAILLÉE & EXPORT"):
        cols = ["transaction_id", "user_id", "amount", "currency", "merchant",
                "country", "card_present", "fraud_score", "risk", "is_suspicious", "reason"]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        e1, e2 = st.columns(2)
        e1.download_button("⬇ Résultats (CSV)",
                           data=view[cols].to_csv(index=False).encode("utf-8"),
                           file_name="resultats_fraude.csv", mime="text/csv")
        e2.download_button("⬇ Verdicts (JSON)",
                           data=pd.Series(results).to_json(orient="values", force_ascii=False),
                           file_name="verdicts.json", mime="application/json")

    st.markdown('<div class="nb-foot">« Construire, c\'est choisir. Automatiser, '
                'c\'est décider. » — LBS 2026</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    render_interface()
