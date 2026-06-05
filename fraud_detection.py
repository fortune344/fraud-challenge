# -*- coding: utf-8 -*-
"""
Détecteur de fraude — Hackathon IT 2026 (Lomé Business School).

Architecture en couches, du plus simple au plus fin :

  Niveau 1 — Robustesse & anomalies évidentes
      • ne plante jamais (champs vides, doublons, horodatages désordonnés)
      • montant nul ou négatif
      • champ obligatoire manquant

  Niveau 2 — Logique métier (chaque transaction est comparée à
             l'HISTORIQUE du même client)
      • montant très supérieur à l'habitude du client (statistique robuste)
      • « voyage impossible » : deux pays incompatibles avec le temps écoulé,
        évalué par distance géographique réelle (haversine) — et non par une
        simple égalité de pays, ce qui évite de pénaliser un trajet plausible
      • fréquence de transactions anormale (rafale)
      • transaction en double (double débit)

  Niveau 3 — Finesse / anti-faux-positifs
      • un écart léger ne déclenche jamais d'alerte (seuils calibrés)
      • toute la logique est calculée, jamais codée en dur

Seule la fonction `detect_fraud` est notée. `load_transactions` est fournie.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime


# --------------------------------------------------------------------------- #
#  Lecture du CSV (fournie par les organisateurs — ne pas perdre de temps ici) #
# --------------------------------------------------------------------------- #
def load_transactions(path):
    """Lit un fichier CSV de transactions et renvoie une liste de dicts."""
    transactions = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append(_clean_row(row))
    return transactions


def _clean_row(row):
    def get(key):
        v = row.get(key)
        return v.strip() if isinstance(v, str) and v.strip() != "" else None

    amount_raw = get("amount")
    try:
        amount = float(amount_raw) if amount_raw is not None else None
    except ValueError:
        amount = None

    card_raw = get("card_present")
    if card_raw is None:
        card_present = None
    else:
        card_present = card_raw.lower() in ("true", "1", "yes", "oui")

    return {
        "transaction_id": get("transaction_id"),
        "timestamp": get("timestamp"),
        "user_id": get("user_id"),
        "amount": amount,
        "currency": get("currency"),
        "merchant": get("merchant"),
        "country": get("country"),
        "card_present": card_present,
    }


# --------------------------------------------------------------------------- #
#  Paramètres de détection (regroupés ici pour la lisibilité et le réglage)    #
# --------------------------------------------------------------------------- #

# Champs sans lesquels une transaction ne peut pas être correctement évaluée.
# (le timestamp est traité à part : il sert au tri et peut être absent)
REQUIRED_FIELDS = ("transaction_id", "user_id", "amount",
                   "currency", "merchant", "country")

# Montant : on ne juge un écart que si l'on dispose d'un historique suffisant.
MIN_HISTORY_FOR_AMOUNT = 3      # nb minimum de montants passés pour comparer
AMOUNT_HIGH_MULTIPLIER = 4.0    # « très supérieur » = au-delà de 4× la médiane
AMOUNT_ABSOLUTE_FLOOR = 50.0    # garde-fou : ignore les écarts en valeur absolue faible
AMOUNT_Z_THRESHOLD = 3.5        # finesse N3 : l'écart doit aussi être un outlier
                                # statistique vis-à-vis de la VARIABILITÉ du client
                                # (un client volatil tolère de plus gros montants)

# Voyage impossible : vitesse de déplacement maximale réaliste (avion direct).
MAX_TRAVEL_SPEED_KMH = 900.0
TRAVEL_TIME_BUFFER = 0.85       # marge : on alerte si le temps écoulé est < 85 %
                                # du temps minimal nécessaire au trajet
UNKNOWN_COUNTRY_MAX_GAP_H = 1.0  # pays inconnu du référentiel : alerte si < 1 h

# Fréquence : rafale de transactions sur une fenêtre très courte.
FREQ_WINDOW_MINUTES = 5
FREQ_MAX_IN_WINDOW = 3          # 3+ transactions en 5 min = anormal

# Double débit : transactions identiques très rapprochées.
DUPLICATE_WINDOW_MINUTES = 2

# Paiement sans carte d'un montant inhabituel (mais sous le seuil « très élevé »).
CARD_ABSENT_MULTIPLIER = 3.0

# Seuil de bascule score -> alerte.
SUSPICION_THRESHOLD = 0.5

# Scores attribués par catégorie (cohérents avec la gravité du signal).
SCORE_NON_POSITIVE = 0.9
SCORE_MISSING = 0.85
SCORE_AMOUNT_HIGH = 0.9
SCORE_IMPOSSIBLE_TRAVEL = 0.88
SCORE_DUPLICATE = 0.7
SCORE_FREQUENCY = 0.7
SCORE_CARD_ABSENT = 0.6
SCORE_CLEAN = 0.0


# Centroïdes approximatifs (lat, lon) pour estimer les distances entre pays.
# Couvre la zone EUR / USD / XOF du sujet ; extensible sans risque.
_COUNTRY_COORDS = {
    "FR": (46.6, 2.2), "BE": (50.5, 4.5), "DE": (51.2, 10.4), "ES": (40.0, -3.7),
    "IT": (41.9, 12.6), "PT": (39.4, -8.2), "NL": (52.1, 5.3), "CH": (46.8, 8.2),
    "GB": (54.0, -2.0), "UK": (54.0, -2.0), "IE": (53.4, -8.2), "LU": (49.8, 6.1),
    "US": (39.8, -98.6), "CA": (56.1, -106.3), "MX": (23.6, -102.5),
    "BR": (-14.2, -51.9), "AR": (-38.4, -63.6),
    "JP": (36.2, 138.3), "CN": (35.9, 104.2), "IN": (20.6, 79.0),
    "KR": (35.9, 127.8), "TH": (15.9, 100.9), "SG": (1.35, 103.8),
    "AE": (23.4, 53.8), "SA": (23.9, 45.1), "TR": (39.0, 35.2),
    "RU": (61.5, 105.3), "AU": (-25.3, 133.8), "ZA": (-30.6, 22.9),
    # Afrique de l'Ouest (zone XOF) :
    "TG": (8.6, 0.8), "BJ": (9.3, 2.3), "CI": (7.5, -5.5), "SN": (14.5, -14.5),
    "ML": (17.6, -4.0), "BF": (12.2, -1.6), "NE": (17.6, 8.1), "GW": (11.8, -15.2),
    "GH": (7.9, -1.0), "NG": (9.1, 8.7), "CM": (7.4, 12.4), "MA": (31.8, -7.1),
    "DZ": (28.0, 1.7), "TN": (33.9, 9.5), "EG": (26.8, 30.8),
}


# --------------------------------------------------------------------------- #
#  Petits utilitaires sûrs (ne lèvent jamais d'exception)                      #
# --------------------------------------------------------------------------- #
def _parse_time(value):
    """Convertit un horodatage ISO 8601 en datetime ; None si impossible."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        # Dernier recours : quelques formats courants.
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip()[:19], fmt)
            except (ValueError, TypeError):
                continue
    return None


def _median(values):
    """Médiane d'une liste de nombres (robuste aux valeurs aberrantes)."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _haversine_km(c1, c2):
    """Distance en km entre deux couples (lat, lon)."""
    lat1, lon1 = c1
    lat2, lon2 = c2
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _hours_between(t1, t2):
    """Écart en heures (positif) entre deux datetimes."""
    return abs((t2 - t1).total_seconds()) / 3600.0


def _is_impossible_travel(country_a, time_a, country_b, time_b):
    """
    Renvoie True si passer de country_a à country_b dans l'intervalle donné
    est physiquement impossible (déplacement plus rapide qu'un avion direct).
    """
    if country_a == country_b:
        return False
    gap_h = _hours_between(time_a, time_b)

    ca = _COUNTRY_COORDS.get(country_a.upper() if country_a else None)
    cb = _COUNTRY_COORDS.get(country_b.upper() if country_b else None)
    if ca is None or cb is None:
        # Référentiel incomplet : on reste prudent (peu d'alertes).
        return gap_h < UNKNOWN_COUNTRY_MAX_GAP_H

    distance = _haversine_km(ca, cb)
    travel_needed_h = distance / MAX_TRAVEL_SPEED_KMH
    return gap_h < travel_needed_h * TRAVEL_TIME_BUFFER


# --------------------------------------------------------------------------- #
#  Analyses contextuelles : on pré-calcule les index suspects par client       #
# --------------------------------------------------------------------------- #
def _group_by_user(transactions):
    """Regroupe les indices de transactions par user_id."""
    groups = {}
    for i, tx in enumerate(transactions):
        uid = tx.get("user_id")
        groups.setdefault(uid, []).append(i)
    return groups


def _flag_impossible_travel(transactions, groups, times):
    """Indices des transactions impliquées dans un saut géographique impossible."""
    flagged = set()
    for indices in groups.values():
        # On ordonne les transactions du client dans le temps.
        timed = [i for i in indices if times[i] is not None
                 and transactions[i].get("country")]
        timed.sort(key=lambda i: times[i])
        for a, b in zip(timed, timed[1:]):
            ca, cb = transactions[a].get("country"), transactions[b].get("country")
            if _is_impossible_travel(ca, times[a], cb, times[b]):
                flagged.add(a)
                flagged.add(b)
    return flagged


def _flag_frequency(transactions, groups, times):
    """Indices appartenant à une rafale (>= N transactions en peu de temps)."""
    flagged = set()
    window = FREQ_WINDOW_MINUTES * 60.0
    for indices in groups.values():
        timed = sorted((i for i in indices if times[i] is not None),
                       key=lambda i: times[i])
        # Fenêtre glissante : pour chaque départ, combien tiennent dans la fenêtre.
        start = 0
        for end in range(len(timed)):
            while (times[timed[end]] - times[timed[start]]).total_seconds() > window:
                start += 1
            if end - start + 1 >= FREQ_MAX_IN_WINDOW:
                for k in range(start, end + 1):
                    flagged.add(timed[k])
    return flagged


def _flag_duplicates(transactions, groups, times):
    """Indices de débits quasi-identiques très rapprochés (double débit)."""
    flagged = set()
    window = DUPLICATE_WINDOW_MINUTES * 60.0
    for indices in groups.values():
        timed = sorted((i for i in indices if times[i] is not None),
                       key=lambda i: times[i])
        for a, b in zip(timed, timed[1:]):
            ta, tb = transactions[a], transactions[b]
            same = (ta.get("amount") is not None
                    and ta.get("amount") == tb.get("amount")
                    and ta.get("merchant") == tb.get("merchant")
                    and ta.get("country") == tb.get("country"))
            close = (times[b] - times[a]).total_seconds() <= window
            if same and close:
                flagged.add(a)
                flagged.add(b)
    return flagged


def _user_amount_history(transactions, groups):
    """Pour chaque transaction, la liste des montants POSITIFS des AUTRES
    transactions du même client (sa dépense « habituelle »)."""
    history = {}
    for indices in groups.values():
        positives = [(i, transactions[i].get("amount")) for i in indices
                     if isinstance(transactions[i].get("amount"), (int, float))
                     and transactions[i].get("amount") > 0]
        for i in indices:
            others = [amt for (j, amt) in positives if j != i]
            history[i] = others
    return history


# --------------------------------------------------------------------------- #
#  Fonction principale                                                         #
# --------------------------------------------------------------------------- #
def detect_fraud(transactions):
    """Analyse une liste de transactions et renvoie un verdict pour chacune.

    Retour : list[dict] avec transaction_id, fraud_score (0-1),
    is_suspicious (bool), reason (str) — un résultat par transaction,
    dans le même ordre.
    """
    # Garde-fou : l'entrée doit être itérable ; sinon on renvoie une liste vide.
    try:
        transactions = list(transactions)
    except TypeError:
        return []

    # Pré-calculs contextuels (robustes : tout champ douteux est neutralisé).
    times = [_parse_time(tx.get("timestamp")) if isinstance(tx, dict) else None
             for tx in transactions]
    groups = _group_by_user(
        [tx if isinstance(tx, dict) else {} for tx in transactions])

    safe_tx = [tx if isinstance(tx, dict) else {} for tx in transactions]
    travel_flags = _flag_impossible_travel(safe_tx, groups, times)
    freq_flags = _flag_frequency(safe_tx, groups, times)
    dup_flags = _flag_duplicates(safe_tx, groups, times)
    amount_history = _user_amount_history(safe_tx, groups)

    results = []
    for i, tx in enumerate(transactions):
        try:
            results.append(
                _evaluate_one(i, tx, travel_flags, freq_flags,
                              dup_flags, amount_history))
        except Exception:
            # Aucune transaction ne doit faire planter le lot.
            tid = tx.get("transaction_id") if isinstance(tx, dict) else None
            results.append({
                "transaction_id": tid,
                "fraud_score": 0.0,
                "is_suspicious": False,
                "reason": "Transaction non analysable (données illisibles)",
            })
    return results


def _is_amount_anomaly(amount, hist):
    """Détecte un montant VRAIMENT anormal pour CE client (anti-faux-positifs).

    Double condition, pour ne jamais crier au loup sur un simple écart :
      1) Relative — le montant dépasse nettement l'habitude (> 4× la médiane)
         avec un garde-fou en valeur absolue ;
      2) Statistique robuste — le montant est un outlier au regard de la PROPRE
         variabilité du client (z-score modifié basé sur la MAD). Un client qui
         dépense 10k–18k ne sera donc pas alerté pour 25k ; un client qui dépense
         toujours 50 le sera pour 250.
    """
    if not (isinstance(amount, (int, float)) and len(hist) >= MIN_HISTORY_FOR_AMOUNT):
        return False
    med = _median(hist)
    if not med or amount <= med:
        return False
    # 1) Garde relatif + absolu
    if amount <= med * AMOUNT_HIGH_MULTIPLIER or amount - med <= AMOUNT_ABSOLUTE_FLOOR:
        return False
    # 2) Garde statistique : outlier vs la variabilité du client
    mad = _median([abs(x - med) for x in hist])
    if mad == 0:
        return True  # client parfaitement régulier : l'écart marqué est suspect
    z = 0.6745 * (amount - med) / mad
    return z >= AMOUNT_Z_THRESHOLD


def _evaluate_one(i, tx, travel_flags, freq_flags, dup_flags, amount_history):
    """Applique les règles par ordre de priorité ; renvoie un verdict unique."""
    if not isinstance(tx, dict):
        tx = {}

    tid = tx.get("transaction_id")
    amount = tx.get("amount")

    def verdict(score, reason):
        return {
            "transaction_id": tid,
            "fraud_score": round(float(score), 4),
            "is_suspicious": bool(score >= SUSPICION_THRESHOLD),
            "reason": reason,
        }

    # --- Niveau 1 : anomalies évidentes ------------------------------------ #
    # 1) Montant nul ou négatif (le montant existe mais est invalide).
    if isinstance(amount, (int, float)) and amount <= 0:
        return verdict(SCORE_NON_POSITIVE, "Montant nul ou négatif")

    # 2) Champs obligatoires manquants.
    missing = [f for f in REQUIRED_FIELDS if tx.get(f) in (None, "")]
    if missing:
        return verdict(SCORE_MISSING,
                       "Champs obligatoires manquants: " + ", ".join(missing))

    # --- Niveau 2 : logique métier ----------------------------------------- #
    # 3) Montant très supérieur à l'habitude du client (et outlier statistique).
    hist = amount_history.get(i, [])
    if _is_amount_anomaly(amount, hist):
        return verdict(SCORE_AMOUNT_HIGH,
                       "Montant très supérieur à l'habitude du client")

    # 4) Deux pays différents en trop peu de temps (voyage impossible).
    if i in travel_flags:
        return verdict(SCORE_IMPOSSIBLE_TRAVEL,
                       "Deux pays différents en trop peu de temps")

    # 5) Transaction en double (double débit).
    if i in dup_flags:
        return verdict(SCORE_DUPLICATE, "Transaction en double suspectée")

    # 6) Fréquence de transactions anormale.
    if i in freq_flags:
        return verdict(SCORE_FREQUENCY, "Fréquence de transactions anormale")

    # 7) Paiement sans carte d'un montant inhabituel (signal plus faible).
    if (tx.get("card_present") is False
            and isinstance(amount, (int, float))
            and len(hist) >= MIN_HISTORY_FOR_AMOUNT):
        med = _median(hist)
        if med and amount > med * CARD_ABSENT_MULTIPLIER:
            return verdict(SCORE_CARD_ABSENT,
                           "Paiement sans carte pour un montant inhabituel")

    # --- Niveau 3 : rien d'anormal ----------------------------------------- #
    return verdict(SCORE_CLEAN, "Transaction conforme au profil du client")


# --------------------------------------------------------------------------- #
#  Profil comportemental par client (utilitaire)                              #
#                                                                             #
#  Fonction SÉPARÉE : elle n'affecte en rien `detect_fraud`. Elle synthétise  #
#  l'historique de chaque client (montant habituel, fréquence, pays et        #
#  commerçants fréquentés) pour le dashboard et l'explicabilité.              #
# --------------------------------------------------------------------------- #
def build_user_profiles(transactions):
    """Construit un profil comportemental pour chaque client.

    Renvoie un dict {user_id: profil} où profil contient le nombre de
    transactions, le montant moyen/médian, l'intervalle médian entre achats,
    et la fréquentation des pays et commerçants.
    """
    try:
        txs = list(transactions)
    except TypeError:
        return {}

    safe = [t if isinstance(t, dict) else {} for t in txs]
    times = [_parse_time(t.get("timestamp")) for t in safe]
    groups = _group_by_user(safe)

    profiles = {}
    for uid, idxs in groups.items():
        amounts = [safe[i].get("amount") for i in idxs
                   if isinstance(safe[i].get("amount"), (int, float))
                   and safe[i].get("amount") > 0]

        countries, merchants = {}, {}
        for i in idxs:
            c = safe[i].get("country")
            if c:
                countries[c] = countries.get(c, 0) + 1
            m = safe[i].get("merchant")
            if m:
                merchants[m] = merchants.get(m, 0) + 1

        ordered = sorted(times[i] for i in idxs if times[i] is not None)
        intervals = [(ordered[k + 1] - ordered[k]).total_seconds() / 3600.0
                     for k in range(len(ordered) - 1)]

        profiles[uid] = {
            "user_id": uid,
            "n_transactions": len(idxs),
            "avg_amount": round(sum(amounts) / len(amounts), 2) if amounts else None,
            "median_amount": _median(amounts) if amounts else None,
            "countries": countries,
            "merchants": merchants,
            "main_country": max(countries, key=countries.get) if countries else None,
            "main_merchant": max(merchants, key=merchants.get) if merchants else None,
            "median_interval_h": round(_median(intervals), 1) if intervals else None,
        }
    return profiles


# --------------------------------------------------------------------------- #
#  Analyse géographique : « voyage impossible » détaillé                       #
#                                                                             #
#  Pour chaque client, repère deux transactions dans des pays différents       #
#  séparées par un temps trop court pour le trajet (distance réelle / vitesse  #
#  d'un avion). Renvoie les détails chiffrés pour l'explicabilité.            #
#  Fonction séparée : n'affecte pas `detect_fraud`.                            #
# --------------------------------------------------------------------------- #
def geo_anomalies(transactions):
    """Renvoie la liste des « voyages impossibles » avec leurs détails.

    Chaque élément : user_id, from, to, distance_km, hours_elapsed,
    hours_needed, tx_ids.
    """
    try:
        txs = list(transactions)
    except TypeError:
        return []

    safe = [t if isinstance(t, dict) else {} for t in txs]
    times = [_parse_time(t.get("timestamp")) for t in safe]
    groups = _group_by_user(safe)

    out = []
    for uid, idxs in groups.items():
        timed = [i for i in idxs if times[i] is not None and safe[i].get("country")]
        timed.sort(key=lambda i: times[i])
        for a, b in zip(timed, timed[1:]):
            ca, cb = safe[a].get("country"), safe[b].get("country")
            if not ca or not cb or ca == cb:
                continue
            ka = _COUNTRY_COORDS.get(ca.upper())
            kb = _COUNTRY_COORDS.get(cb.upper())
            if not ka or not kb:
                continue
            gap_h = _hours_between(times[a], times[b])
            dist = _haversine_km(ka, kb)
            needed = dist / MAX_TRAVEL_SPEED_KMH
            if gap_h < needed * TRAVEL_TIME_BUFFER:
                out.append({
                    "user_id": uid,
                    "from": ca,
                    "to": cb,
                    "distance_km": round(dist),
                    "hours_elapsed": round(gap_h, 2),
                    "hours_needed": round(needed, 1),
                    "tx_ids": [safe[a].get("transaction_id"),
                               safe[b].get("transaction_id")],
                })
    return out


# --------------------------------------------------------------------------- #
#  Prédiction : propension de fraude par client (scorecard explicable)        #
#                                                                             #
#  Sans étiquettes « fraude avérée » on ne peut pas entraîner un modèle        #
#  supervisé : on utilise un SCORECARD pondéré (comme le scoring de crédit),   #
#  transparent et auditable, qui anticipe quel client risque de basculer.     #
#  Fonction séparée : n'affecte pas `detect_fraud`.                           #
# --------------------------------------------------------------------------- #
FORECAST_WEIGHTS = {
    "Taux d'alertes": 0.45,        # part de transactions déjà signalées
    "Volatilité des montants": 0.15,
    "Dispersion géographique": 0.15,
    "Paiements sans carte": 0.15,
    "Activité nocturne": 0.10,
}


def forecast_client_risk(transactions):
    """Prédit une propension de fraude (0–1) par client, avec ses facteurs.

    Renvoie {user_id: {"score", "level", "drivers": [(facteur, contribution)]}}.
    """
    try:
        txs = list(transactions)
    except TypeError:
        return {}

    safe = [t if isinstance(t, dict) else {} for t in txs]
    verdicts = detect_fraud(safe)
    flagged_by_id = {v["transaction_id"]: v["is_suspicious"] for v in verdicts}
    times = [_parse_time(t.get("timestamp")) for t in safe]
    groups = _group_by_user(safe)

    out = {}
    for uid, idxs in groups.items():
        n = len(idxs)
        amounts = [safe[i].get("amount") for i in idxs
                   if isinstance(safe[i].get("amount"), (int, float))
                   and safe[i].get("amount") > 0]
        n_flagged = sum(1 for i in idxs
                        if flagged_by_id.get(safe[i].get("transaction_id")))
        countries = {safe[i].get("country") for i in idxs if safe[i].get("country")}
        n_cnp = sum(1 for i in idxs if safe[i].get("card_present") is False)
        n_night = sum(1 for i in idxs
                      if times[i] is not None and 0 <= times[i].hour <= 5)

        med = _median(amounts) if amounts else 0
        mad = _median([abs(a - med) for a in amounts]) if amounts else 0
        volatility = min(1.0, (mad / med)) if med else 0.0

        feats = {
            "Taux d'alertes": (n_flagged / n) if n else 0.0,
            "Volatilité des montants": volatility,
            "Dispersion géographique": min(1.0, (len(countries) - 1) / 2.0) if countries else 0.0,
            "Paiements sans carte": (n_cnp / n) if n else 0.0,
            "Activité nocturne": (n_night / n) if n else 0.0,
        }
        score = sum(FORECAST_WEIGHTS[k] * v for k, v in feats.items())
        score = round(min(1.0, max(0.0, score)), 3)

        if score >= 0.5:
            level = "Forte"
        elif score >= 0.25:
            level = "Modérée"
        else:
            level = "Faible"

        drivers = sorted(
            ((k, round(FORECAST_WEIGHTS[k] * v, 3)) for k, v in feats.items()),
            key=lambda kv: kv[1], reverse=True)

        out[uid] = {"user_id": uid, "score": score, "level": level,
                    "drivers": [d for d in drivers if d[1] > 0]}
    return out
