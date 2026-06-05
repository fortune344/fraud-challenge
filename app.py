# -*- coding: utf-8 -*-
"""
Tableau de bord Anti-Fraude — Hackathon IT 2026 · Lomé Business School

Design « Radar » : sombre, minimal, dense, orienté analyste.
Branché directement sur le moteur `detect_fraud`.

Lancement :  streamlit run app.py
"""

import csv
import io

import altair as alt
import pandas as pd
import streamlit as st

from fraud_detection import _clean_row, detect_fraud


# --------------------------------------------------------------------------- #
#  Palette & constantes                                                        #
# --------------------------------------------------------------------------- #
RISK_HIGH = 0.85
RISK_MED = 0.5

BG = "#0b0f1a"
PANEL = "#131a2b"
BORDER = "rgba(255,255,255,.07)"
TEXT = "#e8eef9"
MUTED = "#7d8aa6"
ACCENT = "#5b8cff"
DANGER = "#ff5470"
WARN = "#ffae42"
OK = "#2dd4a7"

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
"""


# --------------------------------------------------------------------------- #
#  Helpers de données                                                          #
# --------------------------------------------------------------------------- #
def _risk_level(score):
    if score >= RISK_HIGH:
        return "Élevé"
    if score >= RISK_MED:
        return "Modéré"
    return "Faible"


def _risk_color(score):
    if score >= RISK_HIGH:
        return DANGER
    if score >= RISK_MED:
        return WARN
    return OK


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
    return f"{n:,.0f}".replace(",", " ")


# --------------------------------------------------------------------------- #
#  Style (design Radar)                                                        #
# --------------------------------------------------------------------------- #
CSS = f"""
<style>
  .block-container {{ padding-top: 2.2rem; max-width: 1180px; }}
  #MainMenu, footer {{ visibility: hidden; }}

  .rad-top {{ display:flex; align-items:center; justify-content:space-between;
              margin-bottom:22px; }}
  .rad-brand {{ font-size:19px; font-weight:700; color:{TEXT}; letter-spacing:.2px; }}
  .rad-brand span {{ color:{MUTED}; font-weight:500; font-size:13px; margin-left:8px; }}
  .rad-live {{ display:flex; align-items:center; gap:18px; color:{MUTED}; font-size:13px; }}
  .rad-dot {{ width:8px; height:8px; border-radius:50%; background:{OK};
              display:inline-block; margin-right:6px; animation:rad-pulse 2s infinite; }}
  @keyframes rad-pulse {{ 0%{{box-shadow:0 0 0 0 rgba(45,212,167,.5)}}
                          70%{{box-shadow:0 0 0 7px rgba(45,212,167,0)}}
                          100%{{box-shadow:0 0 0 0 rgba(45,212,167,0)}} }}
  .rad-pill {{ background:rgba(255,84,112,.12); color:{DANGER}; padding:4px 11px;
               border-radius:999px; font-weight:600; font-size:12.5px; }}

  .rad-card {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:16px;
               padding:22px 24px; }}
  .rad-hero-label {{ color:{MUTED}; font-size:12px; letter-spacing:2.5px;
                     font-weight:600; text-transform:uppercase; }}
  .rad-hero-value {{ color:{TEXT}; font-size:52px; font-weight:800; line-height:1.05;
                     margin:8px 0 2px; }}
  .rad-hero-value small {{ font-size:24px; color:{MUTED}; font-weight:600; margin-left:6px; }}
  .rad-hero-foot {{ color:{MUTED}; font-size:13px; margin-top:10px; }}

  .rad-metric {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:14px;
                 padding:16px 18px; height:100%; }}
  .rad-metric .lbl {{ color:{MUTED}; font-size:12px; letter-spacing:.5px;
                      text-transform:uppercase; font-weight:600; }}
  .rad-metric .val {{ color:{TEXT}; font-size:30px; font-weight:800; margin-top:4px; }}

  .rad-sec {{ color:{MUTED}; font-size:12px; letter-spacing:2.5px; font-weight:700;
              text-transform:uppercase; margin:30px 0 14px; }}

  .rad-row {{ display:flex; align-items:center; gap:14px; padding:9px 2px;
              border-bottom:1px solid rgba(255,255,255,.04); }}
  .rad-row .id {{ width:74px; color:{TEXT}; font-weight:600; font-size:13.5px;
                  font-variant-numeric:tabular-nums; }}
  .rad-row .mer {{ width:150px; color:{MUTED}; font-size:13px; overflow:hidden;
                   white-space:nowrap; text-overflow:ellipsis; }}
  .rad-track {{ flex:1; height:9px; background:rgba(255,255,255,.06);
                border-radius:999px; overflow:hidden; }}
  .rad-fill {{ height:100%; border-radius:999px; }}
  .rad-score {{ width:48px; text-align:right; color:{TEXT}; font-weight:700;
                font-size:13.5px; font-variant-numeric:tabular-nums; }}
  .rad-badge {{ width:78px; text-align:center; font-size:11px; font-weight:700;
                letter-spacing:.5px; padding:3px 0; border-radius:7px; }}
</style>
"""


# --------------------------------------------------------------------------- #
#  Composants                                                                  #
# --------------------------------------------------------------------------- #
def _sparkline(values, w=150, h=34):
    if not values:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1.0
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = (i / (n - 1) * w) if n > 1 else w / 2
        y = h - (v - lo) / rng * (h - 6) - 3
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    area = f"0,{h} " + poly + f" {w},{h}"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#sg)"/>'
        f'<polyline points="{poly}" fill="none" stroke="{ACCENT}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def _metric_html(label, value):
    return (f'<div class="rad-metric"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div></div>')


def _risk_rows_html(df_view):
    order = df_view.sort_values("fraud_score", ascending=False)
    rows = []
    for _, r in order.iterrows():
        score = float(r["fraud_score"])
        color = _risk_color(score)
        width = max(score * 100, 2)
        badge_bg = {DANGER: "rgba(255,84,112,.14)", WARN: "rgba(255,174,66,.14)",
                    OK: "rgba(45,212,167,.12)"}[color]
        rows.append(
            f'<div class="rad-row">'
            f'<div class="id">{r["transaction_id"]}</div>'
            f'<div class="mer">{r["merchant"] or "—"}</div>'
            f'<div class="rad-track"><div class="rad-fill" '
            f'style="width:{width:.0f}%;background:{color}"></div></div>'
            f'<div class="rad-score">{score:.2f}</div>'
            f'<div class="rad-badge" style="background:{badge_bg};color:{color}">'
            f'{r["risk"].upper()}</div></div>'
        )
    return "".join(rows)


def _dark_chart(chart):
    return (chart
            .configure_view(strokeWidth=0, fill="transparent")
            .configure(background="transparent")
            .configure_axis(labelColor=MUTED, titleColor=MUTED,
                            gridColor="rgba(255,255,255,.05)",
                            domainColor=BORDER, tickColor=BORDER)
            .configure_legend(labelColor=MUTED, titleColor=MUTED))


# --------------------------------------------------------------------------- #
#  Interface principale                                                        #
# --------------------------------------------------------------------------- #
def render_interface():
    st.set_page_config(page_title="Anti-Fraude · Radar", page_icon="🛡️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    # ---- Barre latérale : données ----------------------------------------- #
    with st.sidebar:
        st.markdown("### Données")
        source = st.radio("Source", ("Jeu d'exemple", "Importer un CSV"),
                          label_visibility="collapsed")
        transactions = None
        if source == "Importer un CSV":
            up = st.file_uploader("Fichier CSV", type=["csv"])
            if up is not None:
                try:
                    transactions = _rows_from_csv_text(up.getvalue().decode("utf-8"))
                except Exception:
                    st.error("Lecture impossible : CSV invalide.")
        else:
            transactions = _rows_from_csv_text(_EXEMPLE_CSV)
        st.caption("Colonnes : transaction_id, timestamp, user_id, amount, "
                   "currency, merchant, country, card_present.")

    if not transactions:
        st.info("⬅️ Importez un CSV ou sélectionnez le jeu d'exemple.")
        st.stop()

    results = detect_fraud(transactions)
    df = _build_dataframe(transactions, results)

    # ---- Filtres ---------------------------------------------------------- #
    with st.sidebar:
        st.markdown("### Filtres")
        niveaux = st.multiselect("Niveau de risque", ["Élevé", "Modéré", "Faible"],
                                 default=["Élevé", "Modéré", "Faible"])
        users = sorted(u for u in df["user_id"].dropna().unique())
        users_sel = st.multiselect("Client", users, default=users)
        only_susp = st.toggle("Seulement les suspectes", value=False)

    view = df[df["risk"].isin(niveaux) & df["user_id"].isin(users_sel)]
    if only_susp:
        view = view[view["is_suspicious"]]

    # ---- Indicateurs ------------------------------------------------------ #
    total = len(df)
    flagged = int(df["is_suspicious"].sum())
    taux = (flagged / total * 100) if total else 0.0
    montant_risque = df.loc[df["is_suspicious"] & (df["amount"] > 0), "amount"].sum()
    score_moyen = df["fraud_score"].mean() if total else 0.0
    currency_ref = (df.loc[df["amount"] > 0, "currency"].mode().iloc[0]
                    if (df["amount"] > 0).any() else "EUR")

    # ---- Barre de titre --------------------------------------------------- #
    st.markdown(
        f"""
        <div class="rad-top">
          <div class="rad-brand">🛡️ Anti-Fraude<span>Radar de transactions · LBS 2026</span></div>
          <div class="rad-live">
            <span><span class="rad-dot"></span>Analyse en direct</span>
            <span class="rad-pill">{flagged}/{total} alertes</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Héro + métriques ------------------------------------------------- #
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        spark = _sparkline(df["fraud_score"].tolist())
        st.markdown(
            f"""
            <div class="rad-card">
              <div class="rad-hero-label">Montant sous surveillance</div>
              <div class="rad-hero-value">{_fmt(montant_risque)}<small>{currency_ref}</small></div>
              <div style="margin-top:8px">{spark}</div>
              <div class="rad-hero-foot">{flagged} alerte(s) sur {total} · taux {taux:.0f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        a, b = st.columns(2)
        a.markdown(_metric_html("Transactions", total), unsafe_allow_html=True)
        b.markdown(_metric_html("Suspectes", flagged), unsafe_allow_html=True)
        c, d = st.columns(2)
        c.markdown(_metric_html("Taux de fraude", f"{taux:.0f}%"), unsafe_allow_html=True)
        d.markdown(_metric_html("Score moyen", f"{score_moyen:.2f}"), unsafe_allow_html=True)

    # ---- Risque par transaction ------------------------------------------ #
    st.markdown('<div class="rad-sec">Risque par transaction</div>',
                unsafe_allow_html=True)
    if len(view):
        st.markdown(f'<div class="rad-card" style="padding:10px 20px">'
                    f'{_risk_rows_html(view)}</div>', unsafe_allow_html=True)
    else:
        st.info("Aucune transaction sur ce périmètre de filtres.")

    # ---- Graphiques ------------------------------------------------------- #
    st.markdown('<div class="rad-sec">Analyse</div>', unsafe_allow_html=True)
    g1, g2 = st.columns(2, gap="medium")

    with g1:
        st.caption("Répartition par niveau de risque")
        rep = (df["risk"].value_counts()
               .reindex(["Élevé", "Modéré", "Faible"]).fillna(0).reset_index())
        rep.columns = ["Niveau", "Nombre"]
        donut = (alt.Chart(rep).mark_arc(innerRadius=62, cornerRadius=3).encode(
            theta="Nombre:Q",
            color=alt.Color("Niveau:N",
                            scale=alt.Scale(domain=["Élevé", "Modéré", "Faible"],
                                            range=[DANGER, WARN, OK]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Niveau", "Nombre"]).properties(height=240))
        st.altair_chart(_dark_chart(donut), use_container_width=True)

    with g2:
        st.caption("Motifs des alertes")
        susp = df[df["is_suspicious"]]
        if len(susp):
            motifs = susp["reason"].value_counts().reset_index()
            motifs.columns = ["Motif", "Nombre"]
            bar = (alt.Chart(motifs).mark_bar(color=ACCENT, cornerRadiusEnd=4).encode(
                x=alt.X("Nombre:Q", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("Motif:N", sort="-x", title=None),
                tooltip=["Motif", "Nombre"]).properties(height=240))
            st.altair_chart(_dark_chart(bar), use_container_width=True)
        else:
            st.success("Aucune alerte sur ce périmètre.")

    # ---- Table & export --------------------------------------------------- #
    with st.expander("Table détaillée & export"):
        cols = ["transaction_id", "user_id", "amount", "currency", "merchant",
                "country", "card_present", "fraud_score", "risk",
                "is_suspicious", "reason"]
        st.dataframe(view[cols], use_container_width=True, hide_index=True)
        e1, e2 = st.columns(2)
        e1.download_button("⬇️ Résultats (CSV)",
                           data=view[cols].to_csv(index=False).encode("utf-8"),
                           file_name="resultats_fraude.csv", mime="text/csv")
        e2.download_button("⬇️ Verdicts (JSON)",
                           data=pd.Series(results).to_json(orient="values",
                                                           force_ascii=False),
                           file_name="verdicts.json", mime="application/json")

    st.caption("« Construire, c'est choisir. Automatiser, c'est décider. » — LBS 2026")


if __name__ == "__main__":
    render_interface()
