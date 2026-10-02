"""Display score line. Stored threshold text stays the raw English formula."""

from __future__ import annotations

from app.i18n import score_line, threshold_crossed


def test_boundary_equal_is_review() -> None:
    line = score_line("es", "review", model_risk_score=1, fraud_score=None, t_low=1, high_value=30)
    assert line == "Puntaje: ≥1.00× umbral · encima → revisión"


def test_rounds_to_one_from_below_stays_automatic() -> None:
    line = score_line("es", "low", model_risk_score=0.995, fraud_score=None, t_low=1, high_value=30)
    assert line == "Puntaje: <1.00× umbral · debajo → automático"


def test_rounds_to_one_from_above_stays_review() -> None:
    line = score_line(
        "es", "review", model_risk_score=1.004, fraud_score=99, t_low=1, high_value=30
    )
    assert line == "Puntaje: ≥1.00× umbral · encima → revisión"


def test_above_ordinary_multiplier() -> None:
    line = score_line("es", "review", model_risk_score=1.02, fraud_score=1, t_low=1, high_value=30)
    assert line == "Puntaje: 1.02× umbral · encima → revisión"


def test_below_ordinary_multiplier() -> None:
    line = score_line("es", "low", model_risk_score=0.85, fraud_score=1, t_low=1, high_value=30)
    assert line == "Puntaje: 0.85× umbral · debajo → automático"


def test_direction_uses_raw_comparison_not_the_band_name() -> None:
    line = score_line("es", "low", model_risk_score=1.02, fraud_score=None, t_low=1, high_value=30)
    assert line == "Puntaje: 1.02× umbral · encima → revisión"


def test_portuguese_uses_a_decimal_comma() -> None:
    above = score_line(
        "pt", "review", model_risk_score=1.02, fraud_score=None, t_low=1, high_value=30
    )
    below = score_line("pt", "low", model_risk_score=0.85, fraud_score=None, t_low=1, high_value=30)
    assert above == "Pontuação: 1,02× limiar · acima → revisão"
    assert below == "Pontuação: 0,85× limiar · abaixo → automático"


def test_high_uses_the_fraud_score() -> None:
    line = score_line("es", "high", model_risk_score=0.99, fraud_score=45, t_low=0.2, high_value=30)
    assert line == "Puntaje de fraude 45 > 30 → bloqueo"
    assert "0.99" not in line
    assert "umbral" not in line
    portuguese = score_line(
        "pt", "high", model_risk_score=0.99, fraud_score=45, t_low=0.2, high_value=30
    )
    assert portuguese == "Pontuação de fraude 45 > 30 → bloqueio"


def test_pending_and_reversed_use_the_rule_sentence() -> None:
    line = score_line(
        "es",
        "out_of_scope",
        model_risk_score=5,
        fraud_score=10,
        t_low=1,
        high_value=30,
    )
    assert line == "Pendiente/Revertido → explicación por regla"
    portuguese = score_line(
        "pt", "out_of_scope", model_risk_score=None, fraud_score=None, t_low=1, high_value=30
    )
    assert portuguese == "Pendente/Revertido → explicação por regra"


def test_missing_model_score_does_not_invent_a_multiplier() -> None:
    line = score_line("es", "review", model_risk_score=None, fraud_score=45, t_low=1, high_value=30)
    assert line == "Puntaje: —"
    assert "×" not in line
    assert "45" not in line


def test_zero_threshold_does_not_divide() -> None:
    line = score_line("es", "low", model_risk_score=1, fraud_score=None, t_low=0, high_value=30)
    assert line == "Puntaje: —"


def test_guardrail_block_has_its_own_score_row() -> None:
    line = score_line(
        "es",
        "out_of_scope",
        model_risk_score=None,
        fraud_score=None,
        t_low=1,
        high_value=30,
        guardrail=True,
    )
    assert line == "Bloqueado por guardrail · sin puntaje"
    assert "Pendiente" not in line
    portuguese = score_line(
        "pt",
        "out_of_scope",
        model_risk_score=5,
        fraud_score=10,
        t_low=1,
        high_value=30,
        guardrail=True,
    )
    assert portuguese == "Bloqueado por guardrail · sem pontuação"
    assert "Pendente" not in portuguese


def test_threshold_crossed_stays_raw_english() -> None:
    assert threshold_crossed("high", fraud_score=45, t_low=0.2, high_value=30) == (
        "fraud_score > 30 (45)"
    )
    assert threshold_crossed("review", fraud_score=None, t_low=1, high_value=30) == "score >= 1"
    assert threshold_crossed("low", fraud_score=None, t_low=1, high_value=30) == "score < 1"
    assert (
        threshold_crossed("out_of_scope", fraud_score=None, t_low=1, high_value=30)
        == "Pending/Reversed"
    )
