"""Dispute case mix ("I don't recognize this charge") for the slides.

Complaints cannot be linked to transactions, so we cannot see which charges were disputed.
We therefore show two scenarios, both built only from saved numbers (no re-scoring, TEST split \
untouched):

A) Base case  - "assumes disputes mirror the charge mix; bands measured on validation split".
   Deterministic ("rule-based") explanation share = Pending + Reversed with fraud_score <= 30
   over ALL transactions (full table). Pending/Reversed with fraud_score > 30 move to HIGH.
   The Approved/Declined share is split HIGH / REVIEW / LOW using VAL band shares (banding_v2).
B) Fraud-only bound - every dispute is real fraud. Band distribution of VAL fraud cases.
   EXTREME BOUND, NOT AN ESTIMATE. LOW here = fraud wrongly auto-handled by the agent.
C) Sensitivity: the 90%-recall t_low (banding_v2.sensitivity_low_90) applied to A and B.

Sources
- /workspace/hack-ml/artifacts/val_results.json  keys banding_v2 (current bands) and \
pending_reversed_high
- /workspace/hack-ml/artifacts/thresholds.json   status_rule and current v2 bands
- /workspace/hackathon-data/cache/bank.duckdb    (READ-ONLY; transaction_status counts)
Run: .venv/bin/python dispute_case_mix.py   -> out/dispute_mix_*.csv, charts/05_dispute_case_mix.png
"""

import json
import os

import duckdb
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT, CH = os.path.join(HERE, "out"), os.path.join(HERE, "charts")
os.makedirs(OUT, exist_ok=True)
os.makedirs(CH, exist_ok=True)
ML_ARTIFACTS = os.environ.get("HACK_ML_ARTIFACTS", "/workspace/hack-ml/artifacts")
VAL = os.path.join(ML_ARTIFACTS, "val_results.json")
THR = os.path.join(ML_ARTIFACTS, "thresholds.json")
DB = os.environ.get("BANK_DUCKDB_PATH", "/workspace/hackathon-data/cache/bank.duckdb")

val_art = json.load(open(VAL))
v2 = val_art["banding_v2"]  # current, non-superseded banding; never use superseded_v1
pr = val_art["pending_reversed_high"]
thr = json.load(open(THR))
BANDS = ["high", "review", "low"]

# ---------- consistency checks between the two ML artifacts ----------
assert thr["version"] == v2["version"], (thr["version"], v2["version"])
assert thr["t_low"] == v2["t_low"]
for b in BANDS:
    assert thr["val"]["bands"][b] == v2["bands"][b], b
assert (
    thr["selection"]["sensitivity_90"]["share_all_in_low"]
    == v2["sensitivity_low_90"]["share_all_in_low"]
)
assert thr["status_rule"]["order"] == [
    "high_rule (fraud_score > 30)",
    "Pending/Reversed shortcut -> out_of_scope",
    "model REVIEW/LOW",
]
assert (
    pr["rule"]
    == "fraud_score > 30 (missing -> not HIGH); runs before the Pending/Reversed \
shortcut"
)

# ---------- full table: status and score counts; fraud labels only train+val ----------
# The TEST split is not read for labels. Full-table score counts are still used for routing/mix.
TEST_START = pr["windows"]["test"].split(">=")[1].strip()
# transaction_date is the DuckDB UTC timestamp
con = duckdb.connect(DB, read_only=True)
st = con.sql(f"""SELECT transaction_status, count(*) AS n,
                       sum(CASE WHEN transaction_date < TIMESTAMP '{TEST_START}' THEN \
is_fraud::INT ELSE 0 END)
                         AS is_fraud_train_val,
                       count(*) FILTER (fraud_score > 30) AS high_gt30,
                       count(*) FILTER (fraud_score > 30 AND transaction_date < TIMESTAMP \
'{TEST_START}' AND is_fraud)
                         AS high_gt30_fraud_train_val,
                       count(*) FILTER (fraud_score > 30 AND transaction_date < TIMESTAMP \
'{TEST_START}' AND NOT is_fraud)
                         AS high_gt30_nonfraud_train_val
                FROM transactions GROUP BY 1 ORDER BY 2 DESC""").df()
con.close()
N_ALL = int(st.n.sum())
n_pend = int(st.loc[st.transaction_status == "Pending", "n"].iloc[0])
n_rev = int(st.loc[st.transaction_status == "Reversed", "n"].iloc[0])
n_ad = N_ALL - n_pend - n_rev
n_pr = n_pend + n_rev
n_pr_high = int(st.loc[st.transaction_status.isin(["Pending", "Reversed"]), "high_gt30"].sum())
n_pr_high_fraud_train_val = int(
    st.loc[st.transaction_status.isin(["Pending", "Reversed"]), "high_gt30_fraud_train_val"].sum()
)
n_pr_high_nonfraud_train_val = int(
    st.loc[
        st.transaction_status.isin(["Pending", "Reversed"]), "high_gt30_nonfraud_train_val"
    ].sum()
)
n_pr_fraud_train_val = int(
    st.loc[st.transaction_status.isin(["Pending", "Reversed"]), "is_fraud_train_val"].sum()
)
st["pct_of_all"] = 100 * st.n / N_ALL
st.to_csv(os.path.join(OUT, "dispute_mix_full_table_status.csv"), index=False)
p_rule, p_pr_high, p_ad = (n_pr - n_pr_high) / N_ALL, n_pr_high / N_ALL, n_ad / N_ALL


# ---------- VAL band table (95% operating point + 90% sensitivity) ----------
def band_rows(bands, label, t_low):
    n_val = sum(bands[b]["n"] for b in BANDS)
    f_val = sum(bands[b]["fraud"] for b in BANDS)
    rows = []
    for b in BANDS:
        d = bands[b]
        rows.append(
            dict(
                operating_point=label,
                t_low_raw=t_low,
                band=b.upper(),
                n=d["n"],
                val_n=n_val,
                share_pct=100 * d["share"],
                fraud=d["fraud"],
                val_fraud=f_val,
                fraud_rate_pct=100 * d["fraud_rate"],
                share_of_fraud_pct=100 * d["share_of_all_fraud"],
            )
        )
    return (
        pd.DataFrame(rows),
        bands["false_auto_close_per_10k_tx"],
        bands["false_auto_close_per_10k_auto_handled"],
    )


val95, fac95, fah95 = band_rows(v2["bands"], "95% recall (v2 chosen)", v2["t_low"])
val90, fac90, fah90 = band_rows(
    v2["sensitivity_low_90"]["bands"], "90% recall (sensitivity)", v2["sensitivity_low_90"]["t_low"]
)
val = pd.concat([val95, val90], ignore_index=True)
val.to_csv(os.path.join(OUT, "dispute_mix_val_bands.csv"), index=False)

# ---------- A) base case and B) fraud-only bound ----------
SEG = {
    "RULE": "Rule-based answer",
    "HIGH": "HIGH (block + handoff)",
    "REVIEW": "REVIEW (handoff)",
    "LOW": "LOW (AI resolves)",
}
mix_rows, fac_rows = [], []
for vb, fac, fah in [(val95, fac95, fah95), (val90, fac90, fah90)]:
    op = vb.operating_point.iloc[0]
    sh = dict(zip(vb.band, vb.share_pct / 100))
    fr = dict(zip(vb.band, vb.share_of_fraud_pct / 100))
    base = {
        "RULE": p_rule,
        "HIGH": p_pr_high + p_ad * sh["HIGH"],
        "REVIEW": p_ad * sh["REVIEW"],
        "LOW": p_ad * sh["LOW"],
    }
    bound = {"RULE": 0.0, **{b: fr[b] for b in ["HIGH", "REVIEW", "LOW"]}}
    for scen, dist, basis, n_basis in [
        (
            "A base case: disputes mirror the charge mix",
            base,
            f"Pending/Reversed score <=30 = rule-based; {n_pr_high:,} Pending/Reversed score >30 = \
HIGH; "
            f"Approved/Declined bands = VAL shares over {n_ad:,} tx (full table)",
            N_ALL,
        ),
        (
            "B fraud-only bound (extreme, not an estimate)",
            bound,
            "VAL fraud cases (Approved/Declined only); Pending/Reversed outside VAL scope",
            int(vb.val_fraud.iloc[0]),
        ),
    ]:
        for k in ["RULE", "HIGH", "REVIEW", "LOW"]:
            mix_rows.append(
                dict(
                    scenario=scen,
                    operating_point=op,
                    segment=SEG[k],
                    pct=100 * dist[k],
                    basis=basis,
                    basis_n=n_basis,
                )
            )
    # wrongful auto-closes (fraud landing in LOW), base case
    fac_rows.append(
        dict(
            operating_point=op,
            per_10k_approved_declined_val=fac,
            per_10k_all_charges_base_case=fac * p_ad,
            per_10k_auto_handled_val=fah,
            fraud_in_low_val=int(vb.loc[vb.band == "LOW", "fraud"].iloc[0]),
            val_n=int(vb.val_n.iloc[0]),
            note="all-charges figure assumes the rule-based path (Pending/Reversed) \
causes no wrongful "
            "fraud closes; it is not model-scored",
        )
    )
mix = pd.DataFrame(mix_rows)
mix.to_csv(os.path.join(OUT, "dispute_mix_scenarios.csv"), index=False)
fac_df = pd.DataFrame(fac_rows)
fac_df.to_csv(os.path.join(OUT, "dispute_mix_wrongful_autoclose.csv"), index=False)

# ---------- verification against reported numbers ----------
b = v2["bands"]
s90 = v2["sensitivity_low_90"]
checks = [
    ("val transactions", 643787, int(val95.val_n.iloc[0])),
    ("val fraud", 599, int(val95.val_fraud.iloc[0])),
    ("HIGH n", 325, b["high"]["n"]),
    ("HIGH share %", 0.050, round(100 * b["high"]["share"], 3)),
    ("HIGH fraud rate %", 100.0, round(100 * b["high"]["fraud_rate"], 1)),
    ("HIGH share of fraud %", 54.3, round(100 * b["high"]["share_of_all_fraud"], 1)),
    ("REVIEW share %", 84.46, round(100 * b["review"]["share"], 2)),
    ("REVIEW fraud rate %", 0.045, round(100 * b["review"]["fraud_rate"], 3)),
    ("REVIEW share of fraud %", 40.9, round(100 * b["review"]["share_of_all_fraud"], 1)),
    ("LOW share %", 15.49, round(100 * b["low"]["share"], 2)),
    ("LOW fraud rate %", 0.029, round(100 * b["low"]["fraud_rate"], 3)),
    ("LOW fraud n", 29, b["low"]["fraud"]),
    ("LOW share of fraud %", 4.8, round(100 * b["low"]["share_of_all_fraud"], 1)),
    ("wrongful auto-closes /10k tx", 0.45, round(b["false_auto_close_per_10k_tx"], 2)),
    (
        "wrongful auto-closes /10k auto-handled",
        2.9,
        round(b["false_auto_close_per_10k_auto_handled"], 1),
    ),
    ("90%: LOW share %", 25.8, round(100 * s90["share_all_in_low"], 1)),
    ("90%: wrongful /10k tx", 0.92, round(s90["false_auto_close_per_10k_tx"], 2)),
    ("full table tx", 4425008, N_ALL),
    ("Pending n", 88343, n_pend),
    ("Pending %", 2.00, round(100 * n_pend / N_ALL, 2)),
    ("Reversed n", 44750, n_rev),
    ("Reversed %", 1.01, round(100 * n_rev / N_ALL, 2)),
    ("Train+val Pending/Reversed fraud n", 106, n_pr_fraud_train_val),
    (
        "Train+val Pending fraud caught by HIGH",
        44,
        int(st.loc[st.transaction_status == "Pending", "high_gt30_fraud_train_val"].iloc[0]),
    ),
    (
        "Train+val Reversed fraud caught by HIGH",
        16,
        int(st.loc[st.transaction_status == "Reversed", "high_gt30_fraud_train_val"].iloc[0]),
    ),
    ("Train+val Pending/Reversed fraud caught by HIGH", 60, n_pr_high_fraud_train_val),
    ("Train+val Pending/Reversed non-fraud sent HIGH", 0, n_pr_high_nonfraud_train_val),
    ("VAL Pending/Reversed fraud n", 11, pr["val"]["Pending+Reversed"]["fraud"]),
    (
        "VAL Pending/Reversed fraud caught HIGH",
        5,
        pr["val"]["Pending+Reversed"]["fraud_caught_high"],
    ),
    ("Train Pending/Reversed fraud n", 95, pr["train"]["Pending+Reversed"]["fraud"]),
    (
        "Train Pending/Reversed fraud caught HIGH",
        55,
        pr["train"]["Pending+Reversed"]["fraud_caught_high"],
    ),
]

ver = pd.DataFrame(checks, columns=["metric", "reported", "from_source"])
ver["match"] = ver.reported == ver.from_source
ver.to_csv(os.path.join(OUT, "dispute_mix_verification.csv"), index=False)

# ---------- chart ----------
COLORS = {
    "Rule-based answer": "#9AA5B1",
    "HIGH (block + handoff)": "#D1495B",
    "REVIEW (handoff)": "#EDAE49",
    "LOW (AI resolves)": "#2E86AB",
}
op95 = "95% recall (v2 chosen)"
m = mix[mix.operating_point == op95]
rows = [
    ("A  Base case\n(disputes mirror charge mix)", m[m.scenario.str.startswith("A")]),
    ("B  Fraud-only bound\n(every dispute is fraud)", m[m.scenario.str.startswith("B")]),
]
fig, ax = plt.subplots(figsize=(12, 4.6), dpi=150)
ypos = [1, 0]
for y, (lab, d) in zip(ypos, rows):
    left = 0
    for _, r in d.iterrows():
        w = r.pct
        ax.barh(
            y,
            w,
            left=left,
            color=COLORS[r.segment],
            height=0.55,
            edgecolor="white",
            linewidth=1.2,
            label=r.segment if y == 1 else None,
        )
        if w >= 6:
            ax.text(
                left + w / 2,
                y,
                f"{w:.1f}%",
                ha="center",
                va="center",
                fontsize=11,
                color="white",
                fontweight="bold",
            )
        left += w
# callouts for thin segments
a = dict(zip(rows[0][1].segment, rows[0][1].pct))
bb = dict(zip(rows[1][1].segment, rows[1][1].pct))
ax.annotate(
    f"Rule-based {a['Rule-based answer']:.1f}%  |  HIGH {a['HIGH (block + handoff)']:.2f}%",
    xy=(a["Rule-based answer"] / 2, 1.28),
    xytext=(0.5, 1.5),
    fontsize=9.5,
    color="#333",
    arrowprops=dict(arrowstyle="-", color="#777", lw=0.8),
    va="center",
)
ax.annotate(
    f"LOW = fraud wrongly auto-handled: {bb['LOW (AI resolves)']:.1f}% (29 of 599)",
    xy=(100 - bb["LOW (AI resolves)"] / 2, -0.28),
    xytext=(60, -0.55),
    fontsize=9.5,
    color="#333",
    arrowprops=dict(arrowstyle="-", color="#777", lw=0.8),
    va="center",
)
ax.set_yticks(ypos)
ax.set_yticklabels([r[0] for r in rows], fontsize=11)
ax.set_xlim(0, 100)
ax.set_ylim(-0.8, 1.75)
ax.set_xticks(range(0, 101, 20))
ax.set_xticklabels([f"{x}%" for x in range(0, 101, 20)], fontsize=9)
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.tick_params(axis="y", length=0)
fig.suptitle(
    'Where "I don\'t recognize this charge" disputes would go',
    x=0.02,
    ha="left",
    fontsize=15,
    fontweight="bold",
    y=0.985,
)
ax.set_title(
    "A assumes disputes mirror the charge mix (rule-based share from all 4.43M tx; bands \
measured on validation "
    "split, n=643,787).\nB is an extreme bound, not an estimate: every dispute is real \
fraud (val fraud n=599).",
    loc="left",
    fontsize=9.5,
    color="#555",
    pad=26,
)
ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.13), frameon=False, fontsize=10)
fig.text(
    0.02,
    0.015,
    f"Base case: {fac95:.2f} wrongful auto-closes per 10k Approved/Declined charges ({
        fac95 * p_ad:.2f} per 10k all charges). "
    f"90%-recall sensitivity: LOW {100 * s90['share_all_in_low']:.1f}% of val, {fac90:.2f} \
per 10k. "
    "Complaints can't be linked to transactions.",
    fontsize=8,
    color="#777",
)
plt.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(os.path.join(CH, "05_dispute_case_mix.png"), bbox_inches="tight")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
print(st.to_string(index=False))
print()
print(val.to_string(index=False))
print()
print(mix.drop(columns=["basis"]).to_string(index=False))
print()
print(fac_df.drop(columns=["note"]).to_string(index=False))
print()
print(ver.to_string(index=False))
