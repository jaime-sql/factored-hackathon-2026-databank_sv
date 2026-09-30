from __future__ import annotations

from app.i18n import packet_merchant, reply_high, reply_pending, reply_review


def test_blank_merchant_uses_category_then_type_then_rewrites() -> None:
    category = reply_pending(
        "es",
        "",
        "159.62 USD",
        "15 ene 2026, 12:00 CST",
        category="Food",
        transaction_type="Purchase",
    )
    assert "El cargo de la categoría Food (159.62 USD)" in category
    assert "de  (" not in category

    typed = reply_high(
        "pt", "  ", "10.00 BRL", "15 jan 2026, 12:00 BRT", transaction_type="Purchase"
    )
    assert "A cobrança do tipo Purchase (10.00 BRL)" in typed
    assert "de  (" not in typed

    bare = reply_review("es", "", "159.62 USD")
    assert bare.startswith("El cargo (159.62 USD)")
    assert "de  (" not in bare

    bare_pt = reply_review("pt", "", "159.62 USD")
    assert bare_pt.startswith("A cobrança (159.62 USD)")


def test_named_merchant_stays_in_the_sentence() -> None:
    text = reply_pending("es", "Farmacia Norte", "159.62 USD", "15 ene 2026, 12:00 CST")
    assert "El cargo de Farmacia Norte (159.62 USD)" in text


def test_packet_merchant_uses_the_same_fallback() -> None:
    assert packet_merchant("es", "Farmacia Norte", "Food", "Purchase") == "Farmacia Norte"
    assert packet_merchant("es", "", "Food", "Purchase") == "categoría Food"
    assert packet_merchant("pt", "", "", "Purchase") == "tipo Purchase"
    assert packet_merchant("es", "", "", "") == "Comercio no identificado"
    assert packet_merchant("pt", "", "", "") == "Comércio não identificado"
