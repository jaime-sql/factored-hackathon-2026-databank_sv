"""Vendored fraud-triage scorer.

The ML package layout is `triage/score.py` plus `triage/artifacts/`.
`score()` applies the team routing order: fraud_score > 30, then Pending/Reversed,
then the LightGBM REVIEW/LOW split.
"""
