"""Demand metrics for transaction-level dispute intake ("I don't recognize this charge").

Source: local DuckDB built by the Data Engineer from the official S3 dataset
  /workspace/hackathon-data/cache/bank.duckdb  (opened READ-ONLY)
Run:  .venv/bin/python demand_metrics.py
Writes every result table as CSV to ./out/ , all SQL to ./demand_metrics.sql, charts to ./charts/.

Definitions
- country / segment = customers.country / customers.segment (customer home country), joined on \
customer_id
  (0 orphan customer_ids in transactions and complaints).
- month = date_trunc('month', transaction_date | creation_date). 2023-06 (from 06-17) and 2026-06 \
(to 06-18) are PARTIAL months.
- high_fraud_score = fraud_score > 30 (fraud_score is NULL for ~20% of rows; NULL counts as not \
flagged).
- case_mix (mutually exclusive, in priority order): HIGH (fraud_score>30) -> Pending -> Reversed \
-> Other.
- dispute_narrow = complaints.category = 'Transactions' (subcategory 'Cargo no reconocido' or NULL).
  dispute_broad  = category IN ('Transactions','Fees')  (Fees subcategory = 'Cobro indebido').
- final status = status IN ('Resolved','Closed','Rejected'); open = Open / In Process / Escalated.
- resolution_days_ts = (COALESCE(resolution_date, closing_date) - creation_date) in days \
(fractional),
  only where both timestamps exist. Cross-checked against the provided resolution_days column.
- SLA: only the boolean column complaints.sla_breached exists. There is NO SLA target/due-date \
column.
"""
import os

import duckdb
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB = os.environ.get("BANK_DUCKDB_PATH", "/workspace/hackathon-data/cache/bank.duckdb")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CH = os.path.join(HERE, "charts")
os.makedirs(OUT, exist_ok=True)
os.makedirs(CH, exist_ok=True)
con = duckdb.connect(DB, read_only=True)

SETUP = """
CREATE OR REPLACE TEMP VIEW tx AS
SELECT t.*, c.country, c.segment, date_trunc('month', t.transaction_date)::DATE AS ym,
       (t.transaction_status='Pending')  AS is_pending,
       (t.transaction_status='Reversed') AS is_reversed,
       (t.fraud_score > 30)              AS is_hi_fs,
       CASE WHEN t.fraud_score > 30              THEN '1 HIGH'
            WHEN t.transaction_status='Pending'  THEN '2 Pending'
            WHEN t.transaction_status='Reversed' THEN '3 Reversed'
            ELSE '4 Other' END AS case_bucket
FROM transactions t JOIN customers c USING (customer_id);

CREATE OR REPLACE TEMP VIEW cp AS
SELECT k.*, c.country, c.segment, date_trunc('month', k.creation_date)::DATE AS ym,
       (k.category='Transactions') AS dispute_narrow,
       (k.category IN ('Transactions','Fees')) AS dispute_broad,
       CASE WHEN k.category='Transactions' THEN 'Transactions (Cargo no reconocido)'
            WHEN k.category='Fees' THEN 'Fees (Cobro indebido)' ELSE 'Other categories' END AS \
cat_group,
       (k.status IN ('Resolved','Closed','Rejected')) AS is_final,
       CASE WHEN COALESCE(k.resolution_date,k.closing_date) IS NOT NULL
            THEN date_diff('second', k.creation_date, COALESCE(k.resolution_date,\
k.closing_date))/86400.0 END AS res_days_ts
FROM complaints k JOIN customers c USING (customer_id);
"""
TX_METRICS = """
  count(*) AS transactions,
  count(*) FILTER (is_pending) AS pending, round(100.0*avg(is_pending::INT),3) AS pending_pct,
  count(*) FILTER (is_reversed) AS reversed, round(100.0*avg(is_reversed::INT),3) AS reversed_pct,
  count(*) FILTER (is_pending OR is_reversed) AS pending_or_reversed,
  round(100.0*avg((is_pending OR is_reversed)::INT),3) AS pending_or_reversed_pct,
  count(*) FILTER (transaction_status='Declined') AS declined,
  count(fraud_score) AS fraud_score_nonnull,
  count(*) FILTER (is_hi_fs) AS fs_gt30, round(100.0*count(*) FILTER (is_hi_fs)/count(*),4) AS \
fs_gt30_pct_all,
  round(100.0*count(*) FILTER (is_hi_fs)/count(fraud_score),4) AS fs_gt30_pct_scored,
  count(*) FILTER (is_hi_fs AND NOT is_pending AND NOT is_reversed) AS fs_gt30_excl_pend_rev,
  count(*) FILTER (is_fraud) AS is_fraud, round(100.0*avg(is_fraud::INT),4) AS is_fraud_pct,
  count(*) FILTER (is_fraud AND is_hi_fs) AS is_fraud_and_fs_gt30
"""
CP_METRICS = """
  count(*) AS complaints,
  count(*) FILTER (dispute_narrow) AS dispute_narrow, round(100.0*avg(dispute_narrow::INT),2) AS \
dispute_narrow_pct,
  count(*) FILTER (dispute_broad) AS dispute_broad, round(100.0*avg(dispute_broad::INT),2) AS \
dispute_broad_pct
"""
RES_METRICS = """
  count(*) AS complaints,
  count(*) FILTER (is_final) AS final_status, round(100.0*avg(is_final::INT),2) AS final_pct,
  count(*) FILTER (status='Resolved') AS resolved, count(*) FILTER (status='Closed') AS closed,
  count(*) FILTER (status='Rejected') AS rejected, count(*) FILTER (status='Open') AS open,
  count(*) FILTER (status='In Process') AS in_process, count(*) FILTER (status='Escalated') AS \
escalated,
  count(res_days_ts) AS n_with_open_and_close_ts,
  round(quantile_cont(res_days_ts,0.5),2) AS res_days_p50, round(quantile_cont(res_days_ts,0.75),\
2) AS res_days_p75,
  round(quantile_cont(res_days_ts,0.9),2) AS res_days_p90, round(avg(res_days_ts),2) AS \
res_days_mean,
  round(quantile_cont(resolution_days,0.5),1) AS col_resolution_days_p50,
  round(quantile_cont(resolution_days,0.75),1) AS col_resolution_days_p75,
  round(quantile_cont(resolution_days,0.9),1) AS col_resolution_days_p90,
  count(*) FILTER (sla_breached) AS sla_breached, round(100.0*avg(sla_breached::INT),2) AS \
sla_breach_pct_all,
  count(*) FILTER (sla_breached AND is_final) AS sla_breached_final,
  round(100.0*count(*) FILTER (sla_breached AND is_final)/NULLIF(count(*) FILTER (is_final),0),2) \
AS sla_breach_pct_final
"""
Q = {}
# 1. transaction side
Q["tx_overall"] = f"SELECT {TX_METRICS} FROM tx"
Q["tx_by_country"] = f"SELECT country, {TX_METRICS} FROM tx GROUP BY 1 ORDER BY 2 DESC"
Q["tx_by_segment"] = f"SELECT segment, {TX_METRICS} FROM tx GROUP BY 1 ORDER BY 2 DESC"
Q["tx_by_country_segment"] = f"SELECT country, segment, {TX_METRICS} FROM tx GROUP BY 1,2 ORDER BY \
1,2"
Q["tx_by_month"] = f"SELECT ym AS month, {TX_METRICS} FROM tx GROUP BY 1 ORDER BY 1"
Q["tx_status_by_is_fraud"] = """SELECT transaction_status, count(*) n, count(fraud_score) scored,
  count(*) FILTER (is_hi_fs) fs_gt30, count(*) FILTER (is_fraud) is_fraud FROM tx GROUP BY 1 ORDER \
BY 2 DESC"""
Q["tx_case_mix"] = """SELECT case_bucket, count(*) n, round(100.0*count(*)/sum(count(*)) OVER (),\
3) pct,
  count(*) FILTER (is_fraud) is_fraud FROM tx GROUP BY 1 ORDER BY 1"""
Q["tx_case_mix_by_country"] = """SELECT country, case_bucket, count(*) n,
  round(100.0*count(*)/sum(count(*)) OVER (PARTITION BY country),3) pct FROM tx GROUP BY 1,2 ORDER \
BY 1,2"""
Q["tx_by_transaction_country_raw"] = """SELECT transaction_country, count(*) n FROM transactions \
GROUP BY 1 ORDER BY 2 DESC"""
# 2. complaint side
Q["cp_categories"] = """SELECT category, subcategory, count(*) n, \
round(100.0*count(*)/sum(count(*)) OVER (),2) pct
  FROM cp GROUP BY 1,2 ORDER BY 1,3 DESC"""
Q["cp_case_type_by_group"] = "SELECT cat_group, case_type, count(*) n FROM cp GROUP BY 1,2 ORDER \
BY 1,3 DESC"
Q["cp_overall"] = f"SELECT {CP_METRICS} FROM cp"
Q["cp_by_country"] = f"SELECT country, {CP_METRICS} FROM cp GROUP BY 1 ORDER BY 2 DESC"
Q["cp_by_segment"] = f"SELECT segment, {CP_METRICS} FROM cp GROUP BY 1 ORDER BY 2 DESC"
Q["cp_by_country_segment"] = f"SELECT country, segment, {CP_METRICS} FROM cp GROUP BY 1,2 ORDER BY \
1,2"
Q["cp_by_month"] = f"""SELECT ym AS month, {CP_METRICS},
  count(*) FILTER (category='Fees') AS fees, count(*) FILTER (NOT dispute_broad) AS other_categories
  FROM cp GROUP BY 1 ORDER BY 1"""
Q["cp_by_channel_group"] = "SELECT reception_channel, cat_group, count(*) n FROM cp GROUP BY 1,2 \
ORDER BY 1,2"
# 3. SLA / resolution
Q["res_overall"] = f"SELECT {RES_METRICS} FROM cp"
Q["res_by_cat_group"] = f"SELECT cat_group, {RES_METRICS} FROM cp GROUP BY 1 ORDER BY 1"
Q["res_by_country"] = f"SELECT country, {RES_METRICS} FROM cp GROUP BY 1 ORDER BY 2 DESC"
Q["res_by_segment"] = f"SELECT segment, {RES_METRICS} FROM cp GROUP BY 1 ORDER BY 2 DESC"
Q["res_disputes_by_country"] = f"SELECT country, {RES_METRICS} FROM cp WHERE dispute_narrow GROUP \
BY 1 ORDER BY 2 DESC"
Q["res_by_priority"] = f"SELECT priority, {RES_METRICS} FROM cp GROUP BY 1 ORDER BY 2 DESC"
Q["res_status_mix"] = """SELECT cat_group, status, count(*) n,
  round(100.0*count(*)/sum(count(*)) OVER (PARTITION BY cat_group),2) pct,
  count(res_days_ts) n_with_dates, count(*) FILTER (sla_breached) sla_breached
  FROM cp GROUP BY 1,2 ORDER BY 1,3 DESC"""
Q["res_days_hist"] = """SELECT cat_group, CAST(floor(res_days_ts) AS INT) AS day_floor, count(*) n
  FROM cp WHERE res_days_ts IS NOT NULL GROUP BY 1,2 ORDER BY 1,2"""
Q["res_check_ts_vs_column"] = """SELECT count(*) FILTER (res_days_ts IS NOT NULL) n_ts, \
count(resolution_days) n_col,
  count(*) FILTER (res_days_ts IS NOT NULL AND resolution_days IS NOT NULL AND \
abs(res_days_ts-resolution_days)>1) n_diff_gt1d
  FROM cp"""
Q["res_sla_vs_days"] = """SELECT sla_breached, count(*) n, count(res_days_ts) n_dates,
  round(quantile_cont(res_days_ts,0.5),2) p50, round(quantile_cont(res_days_ts,0.9),2) p90 FROM cp \
GROUP BY 1"""
# 4. cost-like fields
Q["cost_columns_scan"] = """SELECT table_name, column_name, data_type FROM \
information_schema.columns
  WHERE table_name NOT IN ('tx','cp') AND regexp_matches(lower(column_name),\
'cost|price|fee|salary|wage|amount|compens|duration|handl|effort|budget|value|time_seconds')
  ORDER BY 1,2"""
Q["cost_compensation_by_group"] = """SELECT cat_group, COALESCE(currency,'(null)') currency, \
count(*) complaints,
  count(compensation_granted) n_comp, count(*) FILTER (compensation_granted>0) n_comp_gt0,
  round(sum(compensation_granted),2) sum_comp, round(median(compensation_granted),2) median_comp
  FROM cp GROUP BY 1,2 ORDER BY 1,2"""
Q["cost_callcenter_handle_time"] = """SELECT reason_category, count(*) interactions, \
count(duration_seconds) n_duration,
  round(avg(duration_seconds),1) aht_sec_mean, round(median(duration_seconds),1) aht_sec_p50,
  round(avg(wait_time_seconds),1) wait_sec_mean, round(100*avg(was_resolved::INT),2) resolved_pct,
  round(100*avg(was_escalated::INT),2) escalated_pct, round(100*avg(requires_followup::INT),2) \
followup_pct
  FROM call_center_interactions GROUP BY 1 ORDER BY 2 DESC"""
Q["cost_callcenter_transaccional_by_country_segment"] = """SELECT c.country, c.segment, count(*) \
interactions,
  round(avg(i.duration_seconds),1) aht_sec_mean, round(100*avg(i.was_resolved::INT),2) resolved_pct
  FROM call_center_interactions i JOIN customers c USING (customer_id)
  WHERE i.reason_category='Transaccional' GROUP BY 1,2 ORDER BY 1,2"""
Q["cost_callcenter_by_channel_transaccional"] = """SELECT channel, count(*) interactions, \
round(avg(duration_seconds),1) aht_sec_mean,
  round(100*avg(was_resolved::INT),2) resolved_pct FROM call_center_interactions
  WHERE reason_category='Transaccional' GROUP BY 1 ORDER BY 2 DESC"""

con.execute(SETUP)
with open(os.path.join(HERE, "demand_metrics.sql"), "w") as f:
    f.write("-- Generated by demand_metrics.py; run against \
/workspace/hackathon-data/cache/bank.duckdb (read-only)\n")
    f.write(SETUP + "\n")
    for k, s in Q.items():
        f.write(f"\n-- {k}  -> out/{k}.csv\n{s.strip()};\n")
R = {}
for k, s in Q.items():
    R[k] = con.execute(s).df()
    R[k].to_csv(os.path.join(OUT, f"{k}.csv"), index=False)
    print(f"\n### {k}\n{R[k].to_string(index=False, max_rows=60)}")

# ---------- charts ----------
plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False})
# 1 case mix
m = R["tx_case_mix"]
tot = m.n.sum()
lab = {"1 HIGH": "HIGH\n(fraud_score > 30)",
       "2 Pending": "Pending\n(rule-based answer)",
       "3 Reversed": "Reversed\n(rule-based answer)"}
mm = m[m.case_bucket != "4 Other"]
other = m[m.case_bucket == "4 Other"].iloc[0]
fig, ax = plt.subplots(figsize=(10, 5))
cols = {"1 HIGH": "#E4572E", "2 Pending": "#2E86AB", "3 Reversed": "#59A5D8"}
b = ax.barh([lab[x] for x in mm.case_bucket][::-1], mm.n[::-1],
            color=[cols[x] for x in mm.case_bucket[::-1]])
for rect, n, p in zip(b, mm.n[::-1], mm.pct[::-1]):
    ax.text(rect.get_width() * 1.01, rect.get_y() + rect.get_height() / 2, f"{n:,.0f}  ({p:.2f}%)",\
     va="center")
ax.set_xlim(0, mm.n.max() * 1.35)
ax.set_xlabel("Transactions")
fig.suptitle(f"Transaction case mix: {tot:,.0f} transactions (Jun 2023 – Jun 2026)", x=0.01, \
ha="left", fontweight="bold")
fig.text(0.01, 0.01, f"Mutually exclusive, in priority order HIGH (fraud_score>30) → Pending → \
Reversed. "
         f"Other (Approved/Declined, score ≤30 or null): {other.n:,.0f} ({other.pct:.2f}%).", \
         fontsize=9, color="#555")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(os.path.join(CH, "01_case_mix.png"), dpi=200)
plt.close(fig)

# 2 complaint trend
t = R["cp_by_month"].copy()
t["month"] = pd.to_datetime(t["month"])
fig, ax = plt.subplots(figsize=(11, 5))
ax.stackplot(t.month, t.dispute_narrow, t.fees, t.other_categories,
             labels=["Transactions – 'Cargo no reconocido'", "Fees – 'Cobro indebido'", "Branch / \
Service / Technical"],
             colors=["#E4572E", "#F3A712", "#A8C5DA"])
ax.set_ylabel("Complaints per month")
ax.legend(loc="upper left", frameon=False, fontsize=10)
ax.set_title("Complaint volume by month and category group", loc="left", fontweight="bold")
fig.text(0.01, 0.01, "Source: complaints (67,095). First (Jun-2023, from 17th) and last (Jun-2026, \
to 18th) months are partial.",
         fontsize=9, color="#555")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(os.path.join(CH, "02_complaint_trend.png"), dpi=200)
plt.close(fig)

# 3 resolution days distribution
h = R["res_days_hist"]
r = R["res_by_cat_group"].set_index("cat_group")
fig, ax = plt.subplots(figsize=(10, 5))
d = h[h.cat_group == "Transactions (Cargo no reconocido)"]
a = h.groupby("day_floor").n.sum()
ax.bar(a.index, a.values, color="#A8C5DA", label="All complaints")
ax.bar(d.day_floor, d.n, color="#E4572E", label="Transactions – 'Cargo no reconocido'")
ro = R["res_overall"].iloc[0]
rt = r.loc["Transactions (Cargo no reconocido)"]
for q_, ls in (("res_days_p50", "-"), ("res_days_p75", "--"), ("res_days_p90", ":")):
    ax.axvline(ro[q_], color="#333", ls=ls, lw=1.2, label=f"All {q_[-3:]}: {ro[q_]:.1f} d")
ax.set_xlabel("Days from creation to resolution/closing")
ax.set_ylabel("Complaints")
ax.set_title(f"Resolution time: median {ro.res_days_p50:.1f} d, p90 {ro.res_days_p90:.1f} d "
             f"(disputes: {rt.res_days_p50:.1f} / {rt.res_days_p90:.1f} d)", loc="left", \
             fontweight="bold")
ax.set_ylim(0, ax.get_ylim()[1]*1.3)
ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper center")
fig.text(0.01, 0.01, f"Only complaints with both creation and resolution/closing timestamps: \
n={int(ro.n_with_open_and_close_ts):,} "
         f"of {int(ro.complaints):,} ({100*ro.n_with_open_and_close_ts/ro.complaints:.1f}%).", \
         fontsize=9, color="#555")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(os.path.join(CH, "03_resolution_days.png"), dpi=200)
plt.close(fig)
print("\ncharts written to", CH)
