## 7. Dispute-intake pipeline outputs (added 2026-09-29)

Full details are in `pipeline/README.md`. All numbers below are computed by the pipeline run.
- Silver contract: 0 contract violations. Dedupe: 0 exact duplicates and 0 PK conflicts in transactions (4,425,008), customers (150,000) and products (400,000).
- Country normalization: `México` → `Mexico`. Transactions by country after normalization: Mexico 2,146,309; Colombia 1,289,503; Argentina 867,561; USA 40,621; Spain 40,542; Brazil 40,472. Customers: Mexico 74,907; Colombia 45,251; Argentina 29,842.
- Timestamp offset: fixed +6 h (`transaction_ts_local = transaction_date − 6h`), which keeps every row inside its process_date. 51 rows fall exactly on the closing midnight.
- Fraud-triage table (Approved + Declined only): 4,291,915 rows. Split by UTC time: train 3,004,340 (3,028 positives), val 643,787 (599), test 643,788 (574). Cutoffs 2025-07-26 00:30:11 and 2026-01-07 00:26:41 UTC.
- Baseline `fraud_score >= 30` on test: 422 flagged, 334 true positives, so precision 0.7915 and recall 0.5819 over 574 positives.
- Synthetic duplicate fixture: 300 cases (181 true_duplicate, 119 legitimate_repeat), all `is_synthetic`. It exists because the real data has 0 duplicate charges.
