from __future__ import annotations

from app.i18n import (
    category_label,
    merchant_label,
    packet_merchant,
    reply_high,
    reply_low,
    reply_pending,
    reply_review,
)


def test_blank_merchant_uses_category_then_type_then_rewrites() -> None:
    category = reply_pending(
        "es",
        "",
        "159.62 USD",
        "15 ene 2026, 12:00 CST",
        category="Food",
        transaction_type="Purchase",
    )
    assert "El cargo de la categoría Comida (159.62 USD)" in category
    assert "de  (" not in category

    typed = reply_high(
        "pt", "  ", "10.00 BRL", "15 jan 2026, 12:00 BRT", transaction_type="Purchase"
    )
    assert "A cobrança do tipo Compra (10.00 BRL)" in typed
    assert "de  (" not in typed

    bare = reply_review("es", "", "159.62 USD")
    assert bare.startswith("El cargo (159.62 USD)")
    assert "de  (" not in bare

    bare_pt = reply_review("pt", "", "159.62 USD")
    assert bare_pt.startswith("A cobrança (159.62 USD)")


def test_named_merchant_stays_in_the_sentence() -> None:
    text = reply_pending("es", "Farmacia Norte", "159.62 USD", "15 ene 2026, 12:00 CST")
    assert "El cargo de Farmacia Norte (159.62 USD)" in text


def test_category_titles_drop_the_prefix() -> None:
    """Titles use the category word alone. Sentences still say categoría / categoria."""
    categories = ("Entertainment", "Food", "Health", "Other", "Services", "Transport")
    for category in categories:
        spanish = merchant_label("es", "", category, "Purchase")
        portuguese = merchant_label("pt", "", category, "Purchase")
        assert spanish == category_label("es", category)
        assert portuguese == category_label("pt", category)
        assert not spanish.casefold().startswith("categoría")
        assert not portuguese.casefold().startswith("categoria")
        assert packet_merchant("es", "", category, "Purchase") == spanish
        assert packet_merchant("pt", "", category, "Purchase") == portuguese
    assert merchant_label("es", "", "Transport", "Purchase") == "Transporte"
    assert merchant_label("pt", "", "Transport", "Purchase") == "Transporte"
    sentence = reply_pending(
        "es",
        "",
        "10.00 USD",
        "3 jul 2025, 12:00 COT",
        category="Transport",
        transaction_type="Purchase",
    )
    assert "El cargo de la categoría Transporte (10.00 USD)" in sentence
    portuguese = reply_pending(
        "pt",
        "",
        "10.00 USD",
        "3 jul 2025, 12:00 COT",
        category="Transport",
        transaction_type="Purchase",
    )
    assert "A cobrança da categoria Transporte (10.00 USD)" in portuguese


def test_reply_low_translates_the_category_and_the_charge() -> None:
    spanish = reply_low(
        "es", "Café", "Food", "Bogotá", "1 may 2026", "10.00 USD"
    )
    assert "(Comida)" in spanish
    assert "(Food)" not in spanish
    portuguese = reply_low(
        "pt", "Café", "Food", "São Paulo", "1 mai 2026", "10.00 BRL"
    )
    assert "(Alimentação)" in portuguese
    assert "Food" not in portuguese
    empty = reply_low("pt", "", "", "São Paulo", "1 mai 2026", "10.00 BRL")
    assert "uma cobrança" in empty
    assert "cargo" not in empty


def test_packet_merchant_uses_the_same_fallback() -> None:
    assert packet_merchant("es", "Farmacia Norte", "Food", "Purchase") == "Farmacia Norte"
    assert packet_merchant("es", "", "Food", "Purchase") == "Comida"
    assert packet_merchant("pt", "", "Entertainment", "Purchase") == "Entretenimento"
    assert packet_merchant("pt", "", "", "Purchase") == "Compra"
    assert packet_merchant("es", "", "", "Payment") == "Pago"
    assert packet_merchant("pt", "", "", "Withdrawal") == "Saque"
    assert packet_merchant("es", "", "", "") == "Comercio no identificado"
    assert packet_merchant("pt", "", "", "") == "Comércio não identificado"
