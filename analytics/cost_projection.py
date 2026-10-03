"""Cost-per-resolution PROJECTION for AI-first dispute intake ("I don't recognize this charge").

THIS IS A PROJECTION. Data-derived inputs (handle time, resolution rate, dispute volume) come from
  /workspace/hackathon-data/cache/bank.duckdb (opened READ-ONLY).
Everything in the ASSUMPTIONS block below is an assumption, not data.

Run:  .venv/bin/python cost_projection.py
Writes: out/cost_proj_*.csv, charts/04_cost_projection.png

Formulas
- cost_per_contact     = duration_seconds / 3600 * loaded_cost_per_hour
- cost_per_resolution  = cost_per_contact / resolution_rate
    resolution_rate = share of contacts with was_resolved = TRUE; escalated contacts STAY in the
    denominator (they are not dropped), so they count as cost without (first-contact) resolution.
- monthly_human_cost   = monthly_disputes * cost_per_contact(Queja)      [ASSUMPTION A2]
- sensitivity: human_cost = monthly_disputes * (1 - automated_share) * cost_per_contact(Queja)
               llm_cost   = monthly_disputes * automated_share * LLM_COST_PER_CASE_USD
               net_savings = baseline_human_cost(0% automated) - (human_cost + llm_cost)
"""

import os

import duckdb
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================ ASSUMPTIONS (edit here) ============================
# A1. Fully loaded agent cost per hour, USD, LatAm contact center (wages + benefits + overhead).
WAGE_SCENARIOS_USD_PER_HOUR = {"low": 6.0, "mid": 12.0, "high": 20.0}
# A2. Each dispute complaint (complaints.category='Transactions') costs ONE complaint-type
#     ('Queja') call-center contact at the Queja handle time.
DISPUTE_CONTACT_TYPE = "Queja"
# A3. Handle-time statistic used for the monthly and sensitivity tables ("mean" or "median").
MONTHLY_STAT = "mean"
# A4. LLM/automation cost per automated case, USD. PLACEHOLDER: to be filled by the ML Engineer.
LLM_COST_PER_CASE_USD = None
# A5. Automated share of disputes to test.
AUTOMATION_SHARES = [0.0, 0.25, 0.50, 0.75]
# ================================================================================

DB = os.environ.get("BANK_DUCKDB_PATH", "/workspace/hackathon-data/cache/bank.duckdb")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CH = os.path.join(HERE, "charts")
os.makedirs(OUT, exist_ok=True)
os.makedirs(CH, exist_ok=True)
con = duckdb.connect(DB, read_only=True)
TYPES = ["Transaccional", "Queja"]

# ---- 1. Handle time + resolution (data) ----
# duration_seconds is NULL for every Chat/Email row (voice/video only). Handle time AND resolution
# rate are both computed on the rows WITH a duration so numerator and denominator share a
# population;
# all-contact rates are reported alongside for reference.
ht = con.sql("""
SELECT reason_category AS contact_type,
       count(*)                                         AS interactions_all,
       count(duration_seconds)                          AS interactions_with_duration,
       avg(duration_seconds)                            AS aht_sec_mean,
       median(duration_seconds)                         AS aht_sec_median,
       avg(was_resolved::INT)  FILTER (duration_seconds IS NOT NULL) AS resolution_rate,
       avg(was_escalated::INT) FILTER (duration_seconds IS NOT NULL) AS escalation_rate,
       avg(was_resolved::INT)                           AS resolution_rate_all_contacts,
       avg(was_escalated::INT)                          AS escalation_rate_all_contacts,
       count(*) FILTER (was_resolved AND was_escalated) AS resolved_and_escalated,
       min(interaction_date) AS first_ts, max(interaction_date) AS last_ts
FROM call_center_interactions
WHERE reason_category IN ('Transaccional','Queja')
GROUP BY 1 ORDER BY 1 DESC
""").df()
ht.to_csv(os.path.join(OUT, "cost_proj_inputs_handle_time.csv"), index=False)

# ---- dispute monthly volume (data), full months only ----
mon = con.sql("""
WITH b AS (SELECT min(creation_date) lo, max(creation_date) hi FROM complaints)
SELECT date_trunc('month', creation_date)::DATE AS month, count(*) AS disputes,
       (date_trunc('month', creation_date) = date_trunc('month',(SELECT lo FROM b))
        OR date_trunc('month', creation_date) = date_trunc('month',(SELECT hi FROM b))) AS \
partial_month
FROM complaints WHERE category='Transactions' GROUP BY 1,3 ORDER BY 1
""").df()
mon.to_csv(os.path.join(OUT, "cost_proj_dispute_volume_by_month.csv"), index=False)
full = mon[~mon.partial_month]
DISPUTES_PER_MONTH = full.disputes.mean()

# ---- 1+2. cost per contact / per resolution ----
rows = []
for _, r in ht.iterrows():
    for stat in ["mean", "median"]:
        sec = r[f"aht_sec_{stat}"]
        for scen, rate in WAGE_SCENARIOS_USD_PER_HOUR.items():
            cpc = sec / 3600 * rate
            rows.append(
                dict(
                    contact_type=r.contact_type,
                    handle_time_stat=stat,
                    handle_time_sec=sec,
                    scenario=scen,
                    loaded_usd_per_hour=rate,
                    resolution_rate=r.resolution_rate,
                    cost_per_contact_usd=cpc,
                    cost_per_resolution_usd=cpc / r.resolution_rate,
                )
            )
cpr = pd.DataFrame(rows)
cpr.round(4).to_csv(os.path.join(OUT, "cost_proj_per_resolution.csv"), index=False)

# ---- 3. monthly human cost for dispute volume ----
q = ht.set_index("contact_type").loc[DISPUTE_CONTACT_TYPE]
mrows = []
for stat in ["mean", "median"]:
    for scen, rate in WAGE_SCENARIOS_USD_PER_HOUR.items():
        cpc = q[f"aht_sec_{stat}"] / 3600 * rate
        mrows.append(
            dict(
                scenario=scen,
                loaded_usd_per_hour=rate,
                handle_time_stat=stat,
                disputes_per_month=DISPUTES_PER_MONTH,
                cost_per_contact_usd=cpc,
                monthly_human_cost_usd=DISPUTES_PER_MONTH * cpc,
                # reference only: if every dispute needed contacts until resolved
                monthly_cost_if_per_resolution_usd=DISPUTES_PER_MONTH * cpc / q.resolution_rate,
            )
        )
monthly = pd.DataFrame(mrows)
monthly.round(2).to_csv(os.path.join(OUT, "cost_proj_monthly_disputes.csv"), index=False)

# ---- 4. sensitivity: automated share x wage scenario ----
srows = []
for scen, rate in WAGE_SCENARIOS_USD_PER_HOUR.items():
    cpc = q[f"aht_sec_{MONTHLY_STAT}"] / 3600 * rate
    base = DISPUTES_PER_MONTH * cpc
    for a in AUTOMATION_SHARES:
        human = DISPUTES_PER_MONTH * (1 - a) * cpc
        if LLM_COST_PER_CASE_USD is None:
            llm, net = "TBD", "TBD"
        else:
            llm = DISPUTES_PER_MONTH * a * LLM_COST_PER_CASE_USD
            net = round(base - (human + llm), 2)
            llm = round(llm, 2)
        srows.append(
            dict(
                scenario=scen,
                loaded_usd_per_hour=rate,
                automated_share=a,
                human_cases_per_month=round(DISPUTES_PER_MONTH * (1 - a), 1),
                projected_monthly_human_cost_usd=round(human, 2),
                human_cost_avoided_usd=round(base - human, 2),
                llm_cost_per_case_usd="TBD"
                if LLM_COST_PER_CASE_USD is None
                else LLM_COST_PER_CASE_USD,
                monthly_llm_cost_usd=llm,
                net_monthly_savings_usd=net,
            )
        )
sens = pd.DataFrame(srows)
sens.to_csv(os.path.join(OUT, "cost_proj_sensitivity_automation.csv"), index=False)

# ---- 5. chart ----
d = (
    cpr[cpr.handle_time_stat == "mean"]
    .pivot(index="scenario", columns="contact_type", values="cost_per_resolution_usd")
    .loc[list(WAGE_SCENARIOS_USD_PER_HOUR)]
)
fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
colors = {"Transaccional": "#4C78A8", "Queja": "#E45756"}
w = 0.36
x = range(len(d))
for i, t in enumerate(TYPES):
    xs = [xi + (i - 0.5) * w for xi in x]
    bars = ax.bar(
        xs,
        d[t],
        w,
        label=f"{t}  (AHT {ht.set_index('contact_type').loc[t, 'aht_sec_mean']:.0f}s, "
        f"{100 * ht.set_index('contact_type').loc[t, 'resolution_rate']:.1f}% resolved)",
        color=colors[t],
    )
    for b in bars:
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height() + 0.08,
            f"${b.get_height():.2f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )
ax.set_xticks(list(x))
ax.set_xticklabels(
    [f"{s.capitalize()}\n${r:.0f}/h loaded" for s, r in WAGE_SCENARIOS_USD_PER_HOUR.items()],
    fontsize=11,
)
ax.set_ylabel("Human cost per resolution (USD)", fontsize=11)
fig.suptitle(
    "Human cost per resolution: Transaccional vs Queja", fontsize=15, fontweight="bold", y=0.97
)
ax.set_title(
    "Projection. Wage rates are assumptions; handle times and resolution rates come from \
call-center logs.",
    fontsize=9.5,
    color="#555555",
    pad=10,
)
ax.spines[["top", "right"]].set_visible(False)
ax.set_ylim(0, d.values.max() * 1.18)
ax.legend(frameon=False, fontsize=10, loc="upper left")
fig.text(
    0.01,
    0.01,
    "Cost per resolution = (mean handle time / 3600 x loaded $/h) / resolution \
rate. "
    "Escalated contacts kept in denominator. Voice/video contacts only (chat/email have no \
duration).",
    fontsize=7.5,
    color="#777777",
)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(os.path.join(CH, "04_cost_projection.png"))
plt.close(fig)

# ---- console summary ----
pd.set_option("display.width", 200)
print(ht.T)
print(
    f"\nDisputes/month (full months {full.month.min()}..{full.month.max()}, n={len(full)}): "
    f"mean {DISPUTES_PER_MONTH:.1f}, min {full.disputes.min()}, max \
{full.disputes.max()}"
)
print(cpr.round(3).to_string(index=False))
print(monthly.round(2).to_string(index=False))
print(sens.to_string(index=False))
