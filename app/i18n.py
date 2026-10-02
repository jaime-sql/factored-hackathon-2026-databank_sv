"""Spanish (LATAM) and Portuguese templates.

Portuguese strings are machine-translated and must be reported as language=pt,
never as production traffic from Portuguese-speaking customers. The bank's
customers in this slice are in MX, CO, and AR.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PT_MARKERS = (
    "não",
    "nao",
    "reconheço",
    "reconheco",
    "cobrança",
    "cobranca",
    "cartão",
    "cartao",
    "você",
    "voce",
    "estornada",
    "pendente",
)


def detect_language(text: str, override: str | None = None) -> str:
    if override in {"es", "pt"}:
        return override
    lowered = text.lower()
    if any(marker in lowered for marker in PT_MARKERS):
        return "pt"
    return "es"


_TRANSACTION_TYPES = {
    "es": {
        "Adjustment": "Ajuste",
        "Deposit": "Depósito",
        "Payment": "Pago",
        "Purchase": "Compra",
        "Transfer": "Transferencia",
        "Withdrawal": "Retiro",
    },
    "pt": {
        "Adjustment": "Ajuste",
        "Deposit": "Depósito",
        "Payment": "Pagamento",
        "Purchase": "Compra",
        "Transfer": "Transferência",
        "Withdrawal": "Saque",
    },
}
_REGION_CODES = {
    "ar": "AR",
    "argentina": "AR",
    "br": "BR",
    "brazil": "BR",
    "brasil": "BR",
    "co": "CO",
    "colombia": "CO",
    "colômbia": "CO",
    "mx": "MX",
    "mexico": "MX",
    "méxico": "MX",
    "es": "ES",
    "spain": "ES",
    "españa": "ES",
    "espanha": "ES",
    "us": "US",
    "usa": "US",
    "u.s.a.": "US",
    "united states": "US",
    "estados unidos": "US",
}
_COUNTRY_NAMES = {
    "es": {
        "AR": "Argentina",
        "BR": "Brasil",
        "CO": "Colombia",
        "MX": "México",
        "ES": "España",
        "US": "Estados Unidos",
    },
    "pt": {
        "AR": "Argentina",
        "BR": "Brasil",
        "CO": "Colômbia",
        "MX": "México",
        "ES": "Espanha",
        "US": "Estados Unidos",
    },
}


def _ui_language(language: str) -> str:
    return "pt" if language == "pt" else "es"


def money(amount: float, currency: str, country: str = "") -> str:
    """Format by the customer's country, not the UI language.

    Mexico uses comma thousands, a dot decimal, and no space (US$1,645.60).
    Every other country uses dot thousands, a comma decimal, and a space (US$ 1.645,60).
    """
    try:
        quant = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError):
        return (currency or "").strip()
    sign = "-" if quant < 0 else ""
    whole, frac = f"{abs(quant):.2f}".split(".")
    groups: list[str] = []
    digits = whole
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    mexico = _region_code(country) == "MX"
    grouped = ",".join(reversed(groups)) if mexico else ".".join(reversed(groups))
    number = f"{grouped}.{frac}" if mexico else f"{grouped},{frac}"
    code = (currency or "").strip().upper()
    if not code:
        return f"{sign}{number}"
    label = "US$" if code == "USD" else code
    gap = "" if mexico else " "
    return f"{sign}{label}{gap}{number}"


_CATEGORIES = {
    "es": {
        "Entertainment": "Entretenimiento",
        "Food": "Comida",
        "Health": "Salud",
        "Other": "Otros",
        "Services": "Servicios",
        "Transport": "Transporte",
    },
    "pt": {
        "Entertainment": "Entretenimento",
        "Food": "Alimentação",
        "Health": "Saúde",
        "Other": "Outros",
        "Services": "Serviços",
        "Transport": "Transporte",
    },
}
_CATEGORY_KEYS = {
    label.casefold(): key for table in _CATEGORIES.values() for key, label in table.items()
}
_CATEGORY_KEYS.update({key.casefold(): key for key in _CATEGORIES["es"]})
_BANDS = {
    "es": {
        "high": "Alto",
        "low": "Bajo",
        "review": "Revisión",
        "out_of_scope": "Fuera de alcance",
    },
    "pt": {
        "high": "Alto",
        "low": "Baixo",
        "review": "Revisão",
        "out_of_scope": "Fora de escopo",
    },
}
_ACTION_PHRASES = {
    "es": {
        "block_card verified": "Bloqueo de tarjeta verificado",
        "block_card failed": "Bloqueo de tarjeta fallido",
        "handoff verified": "Traspaso verificado",
        "handoff failed": "Traspaso fallido",
        "decline_block not_applicable": "Bloqueo no aplicado",
        "contest not_applicable": "Impugnación registrada",
        "open_dispute not_applicable": "Disputa abierta",
    },
    "pt": {
        "block_card verified": "Bloqueio de cartão verificado",
        "block_card failed": "Bloqueio de cartão falhou",
        "handoff verified": "Repasse verificado",
        "handoff failed": "Repasse falhou",
        "decline_block not_applicable": "Bloqueio não aplicado",
        "contest not_applicable": "Contestação registrada",
        "open_dispute not_applicable": "Disputa aberta",
    },
}
_DECISIONS = {
    "es": {"handoff": "Traspaso"},
    "pt": {"handoff": "Repasse"},
}


def transaction_type_label(language: str, transaction_type: str) -> str:
    cleaned = (transaction_type or "").strip()
    if not cleaned:
        return ""
    return _TRANSACTION_TYPES[_ui_language(language)].get(cleaned, cleaned)


def category_label(language: str, category: str) -> str:
    cleaned = (category or "").strip()
    if not cleaned:
        return ""
    key = _CATEGORY_KEYS.get(cleaned.casefold())
    if key is None:
        return cleaned
    return _CATEGORIES[_ui_language(language)][key]


def band_label(language: str, band: str) -> str:
    cleaned = (band or "").strip()
    if not cleaned:
        return ""
    return _BANDS[_ui_language(language)].get(cleaned, cleaned)


def action_phrase(language: str, name: str, status: str) -> str:
    key = f"{(name or '').strip()} {(status or '').strip()}".strip()
    if not key:
        return ""
    return _ACTION_PHRASES[_ui_language(language)].get(key, key)


def decision_label(language: str, decision: str) -> str:
    cleaned = (decision or "").strip()
    if not cleaned:
        return ""
    return _DECISIONS[_ui_language(language)].get(cleaned, cleaned)


def _region_code(value: str) -> str:
    return _REGION_CODES.get((value or "").strip().lower(), "")


def place_label(city: str, country: str, home: str, language: str) -> str:
    """City, and the localized country when the charge is outside the customer's country.

    A missing country leaves the city. Empty pieces are dropped before joining.
    """
    city_text = (city or "").strip()
    code = _region_code(country)
    if not code or code == _region_code(home):
        return city_text
    name = _COUNTRY_NAMES[_ui_language(language)].get(code, "")
    return ", ".join(part for part in (city_text, name) if part)


def merchant_label(language: str, name: str, category: str, transaction_type: str) -> str:
    """Readable merchant for replies. Empty when name, category, and type are blank."""
    cleaned_name = (name or "").strip()
    if cleaned_name:
        return cleaned_name
    cleaned_category = (category or "").strip()
    if cleaned_category:
        return category_label(language, cleaned_category)
    label = transaction_type_label(language, transaction_type)
    if label:
        return label
    return ""


def packet_merchant(language: str, name: str, category: str, transaction_type: str) -> str:
    """Same fallback as replies. A last resort label keeps the handoff packet complete."""
    label = merchant_label(language, name, category, transaction_type)
    if label:
        return label
    if language == "pt":
        return "Comércio não identificado"
    return "Comercio no identificado"


def _charge_with_amount(
    language: str, name: str, category: str, transaction_type: str, amount: str
) -> str:
    label = merchant_label(language, name, category, transaction_type)
    if language == "pt":
        if not (name or "").strip() and (category or "").strip():
            label = category_label(language, category)
            return f"A cobrança da categoria {label} ({amount})"
        typed = transaction_type_label(language, transaction_type)
        if not (name or "").strip() and not (category or "").strip() and typed:
            return f"A cobrança do tipo {typed} ({amount})"
        if label:
            return f"A cobrança de {label} ({amount})"
        return f"A cobrança ({amount})"
    if not (name or "").strip() and (category or "").strip():
        label = category_label(language, category)
        return f"El cargo de la categoría {label} ({amount})"
    typed = transaction_type_label(language, transaction_type)
    if not (name or "").strip() and not (category or "").strip() and typed:
        return f"El cargo de tipo {typed} ({amount})"
    if label:
        return f"El cargo de {label} ({amount})"
    return f"El cargo ({amount})"


def contest_label(language: str) -> str:
    if language == "pt":
        return "Continuo sem reconhecer esta cobrança"
    return "Sigo sin reconocer este cargo"


def confirm_block_label(language: str) -> str:
    if language == "pt":
        return "Sim, bloquear o cartão"
    return "Sí, bloquear la tarjeta"


def decline_block_label(language: str) -> str:
    if language == "pt":
        return "Agora não"
    return "Ahora no"


def recognize_label(language: str) -> str:
    if language == "pt":
        return "Agora reconheço este comércio"
    return "Ahora reconozco este comercio"


def dispute_label(language: str) -> str:
    if language == "pt":
        return "Não reconheço: abrir uma revisão humana"
    return "No lo reconozco: abrir una revisión humana"


def _contest_footer(language: str) -> str:
    label = contest_label(language)
    if language == "pt":
        return (
            f"Se ainda não reconhece esta cobrança, passe o caso a uma pessoa. "
            f"A opção em destaque é «{label}»."
        )
    return (
        f"Si sigue sin reconocer este cargo, páselo a una persona. "
        f"La opción destacada es «{label}»."
    )


def reply_pending(
    language: str,
    merchant: str,
    amount: str,
    when: str,
    *,
    category: str = "",
    transaction_type: str = "",
) -> str:
    charge = _charge_with_amount(language, merchant, category, transaction_type, amount)
    if language == "pt":
        body = (
            f"{charge} em {when} ainda está pendente. "
            "Ainda não é definitiva, então não há o que contestar agora. "
            "Nenhum dinheiro foi movido por este assistente."
        )
    else:
        body = (
            f"{charge} del {when} sigue pendiente. "
            "Todavía no es definitivo, así que no hay nada que disputar. "
            "Este asistente no movió dinero."
        )
    return body + "\n\n" + _contest_footer(language)


def reply_reversed(
    language: str,
    merchant: str,
    amount: str,
    when: str,
    *,
    category: str = "",
    transaction_type: str = "",
) -> str:
    charge = _charge_with_amount(language, merchant, category, transaction_type, amount)
    if language == "pt":
        body = (
            f"{charge} em {when} já foi estornada. "
            "O valor já voltou. Este assistente não moveu dinheiro."
        )
    else:
        body = (
            f"{charge} del {when} ya fue reversado. "
            "El dinero ya regresó. Este asistente no movió dinero."
        )
    return body + "\n\n" + _contest_footer(language)


def reply_high(
    language: str,
    merchant: str,
    amount: str,
    when: str,
    *,
    category: str = "",
    transaction_type: str = "",
) -> str:
    charge = _charge_with_amount(language, merchant, category, transaction_type, amount)
    if language == "pt":
        return (
            f"{charge} em {when} supera a regra de risco "
            "(pontuação de fraude maior que 30). Podemos bloquear o cartão. "
            "O bloqueio só acontece se você confirmar. Nenhum dinheiro foi movido."
        )
    return (
        f"{charge} del {when} supera la regla de riesgo "
        "(puntaje de fraude mayor que 30). Podemos bloquear la tarjeta. "
        "El bloqueo solo se hace si usted lo confirma. No se movió dinero."
    )


def reply_low(
    language: str,
    merchant: str,
    category: str,
    city: str,
    when: str,
    amount: str,
    *,
    transaction_type: str = "",
) -> str:
    label = merchant_label(language, merchant, category, transaction_type)
    if language == "pt":
        if (merchant or "").strip():
            found = f"Encontrei {merchant} ({category}) em {city}, {when}, por {amount}."
        elif label:
            found = f"Encontrei um comércio ({label}) em {city}, {when}, por {amount}."
        else:
            found = f"Encontrei um cargo em {city}, {when}, por {amount}."
        return (
            f"{found} "
            "Está no seu histórico. Se agora reconhece o comércio, fechamos o caso. "
            "Se não, uma pessoa revisa. Nenhum dinheiro foi movido."
        )
    if (merchant or "").strip():
        found = f"Encontré {merchant} ({category}) en {city}, el {when}, por {amount}."
    elif label:
        found = f"Encontré un comercio ({label}) en {city}, el {when}, por {amount}."
    else:
        found = f"Encontré un cargo en {city}, el {when}, por {amount}."
    return (
        f"{found} "
        "Está en su historial. Si ahora reconoce el comercio, cerramos el caso. "
        "Si no, una persona lo revisa. No se movió dinero."
    )


def reply_review(
    language: str,
    merchant: str,
    amount: str,
    *,
    category: str = "",
    transaction_type: str = "",
) -> str:
    charge = _charge_with_amount(language, merchant, category, transaction_type, amount)
    if language == "pt":
        return (
            f"{charge} precisa de uma pessoa. "
            "Não oferecemos bloqueio do cartão neste caso. Nenhum dinheiro foi movido."
        )
    return (
        f"{charge} necesita una persona. "
        "No ofrecemos bloquear la tarjeta en este caso. No se movió dinero."
    )


def reply_duplicate(
    language: str,
    merchant: str,
    amount: str,
    when: str,
    other_when: str,
    *,
    category: str = "",
    transaction_type: str = "",
) -> str:
    label = merchant_label(language, merchant, category, transaction_type)
    if language == "pt":
        if not (merchant or "").strip() and (category or "").strip():
            label = category_label(language, category)
            head = f"Há um possível duplicado SINTÉTICO da categoria {label} ({amount})"
        elif label:
            head = f"Há um possível duplicado SINTÉTICO de {label} ({amount})"
        else:
            head = f"Há um possível duplicado SINTÉTICO ({amount})"
        return (
            f"{head}: {when} e {other_when}. "
            "Este par vem do cenário de teste de duplicados sintéticos, não de um duplicado real. "
            "Se reconhece o comércio, fechamos. Se não, uma pessoa revisa. Nenhum dinheiro foi movido."
        )
    if not (merchant or "").strip() and (category or "").strip():
        label = category_label(language, category)
        head = f"Hay un posible duplicado SINTÉTICO de la categoría {label} ({amount})"
    elif label:
        head = f"Hay un posible duplicado SINTÉTICO de {label} ({amount})"
    else:
        head = f"Hay un posible duplicado SINTÉTICO ({amount})"
    return (
        f"{head}: {when} y {other_when}. "
        "Este par sale del escenario de prueba de duplicados sintéticos, no de un duplicado real. "
        "Si reconoce el comercio, cerramos. Si no, una persona revisa. No se movió dinero."
    )


def reply_blocked(language: str, case_id: str) -> str:
    if language == "pt":
        return (
            f"Bloqueei o cartão e verifiquei o registro. O caso {case_id} passou a uma pessoa. "
            "Nenhum dinheiro foi movido."
        )
    return (
        f"Bloqueé la tarjeta y verifiqué el registro. El caso {case_id} pasó a una persona. "
        "No se movió dinero."
    )


def reply_block_failed(language: str, case_id: str) -> str:
    if language == "pt":
        return (
            f"Não confirmei o bloqueio na leitura de verificação. O caso {case_id} passou a uma pessoa. "
            "Não diga que o cartão está bloqueado. Nenhum dinheiro foi movido."
        )
    return (
        f"No pude confirmar el bloqueo en la lectura de verificación. El caso {case_id} pasó a una persona. "
        "No dé por bloqueada la tarjeta. No se movió dinero."
    )


def reply_declined_block(language: str, case_id: str) -> str:
    if language == "pt":
        return (
            f"Não bloqueei o cartão. O caso {case_id} passou a uma pessoa porque a regra de risco segue ativa. "
            "Nenhum dinheiro foi movido."
        )
    return (
        f"No bloqueé la tarjeta. El caso {case_id} pasó a una persona porque la regla de riesgo sigue activa. "
        "No se movió dinero."
    )


def reply_contested(language: str, case_id: str) -> str:
    if language == "pt":
        return (
            f"Entendi: você continua sem reconhecer a cobrança. O caso {case_id} está com uma pessoa. "
            "Nenhum dinheiro foi movido."
        )
    return (
        f"Entendido: sigue sin reconocer el cargo. El caso {case_id} quedó con una persona. "
        "No se movió dinero."
    )


def reply_recognized(language: str) -> str:
    if language == "pt":
        return "Fechamos o caso porque você reconheceu o comércio. Nenhum dinheiro foi movido."
    return "Cerramos el caso porque reconoció el comercio. No se movió dinero."


def reply_dispute_opened(language: str, case_id: str) -> str:
    if language == "pt":
        return f"Abri uma revisão humana do caso {case_id}. Nenhum crédito foi emitido e nenhum dinheiro foi movido."
    return f"Abrí una revisión humana del caso {case_id}. No se emitió un crédito y no se movió dinero."


def reply_clarify(language: str) -> str:
    if language == "pt":
        return "Escolha uma cobrança da sua lista e diga que não a reconhece. Não movo dinheiro."
    return "Elija un cargo de su lista y diga que no lo reconoce. No muevo dinero."


def reply_injection(language: str) -> str:
    if language == "pt":
        return (
            "Protegido. Não reembolso, não emito um crédito e não mudo as regras. "
            "Só posso ajudar com uma cobrança da sua lista."
        )
    return (
        "Protegido. No reembolso, no emito un crédito y no cambio las reglas. "
        "Solo puedo ayudar con un cargo de su lista."
    )


def reply_permission(language: str) -> str:
    if language == "pt":
        return "Essa ação não está permitida neste estado do caso. Nenhum dinheiro foi movido."
    return "Esa acción no está permitida en este estado del caso. No se movió dinero."


def next_step_block(language: str) -> str:
    if language == "pt":
        return "Revisar o cartão bloqueado e falar com o cliente. Nenhum crédito foi emitido."
    return "Revisar la tarjeta bloqueada y contactar al cliente. No se emitió un crédito."


def next_step_review(language: str) -> str:
    if language == "pt":
        return "Revisar a cobrança com uma pessoa. Não bloquear o cartão a partir deste pacote. Nenhum crédito foi emitido."
    return "Revisar el cargo con una persona. No bloquear la tarjeta desde este paquete. No se emitió un crédito."


def mask_merchant(label: str) -> str:
    """Mask every merchant label the same way, including category fallbacks."""
    text = (label or "").strip()
    if not text:
        return ""
    masked: list[str] = []
    for word in text.split():
        masked.append(word if len(word) <= 1 else word[0] + ("•" * (len(word) - 1)))
    return " ".join(masked)


def handoff_reason_label(
    language: str,
    reason: str,
    *,
    band: str,
    case_type: str,
    synthetic: bool,
    card_blocked: bool,
) -> str:
    """Short queue label. A LOW card is only the customer's request for a person."""
    pt = language == "pt"
    if band == "low" and reason == "customer_requested_human":
        label = (
            "Cliente pediu uma pessoa (risco baixo)"
            if pt
            else "Cliente pidió una persona (riesgo bajo)"
        )
        if synthetic:
            extra = "Possível duplicado" if pt else "Posible duplicado"
            return f"{label} · {extra}"
        return label
    if synthetic and reason == "fraud_model":
        return "Possível duplicado" if pt else "Posible duplicado"
    if reason == "customer_contests_rule_answer":
        if case_type == "reversed":
            return (
                "Cliente contestou a explicação (estornada)"
                if pt
                else "Cliente impugnó explicación (reversado)"
            )
        return (
            "Cliente contestou a explicação (pendente)"
            if pt
            else "Cliente impugnó explicación (pendiente)"
        )
    if reason == "fraud_rule" and card_blocked:
        return "Risco alto: cartão bloqueado" if pt else "Riesgo alto: tarjeta bloqueada"
    if reason == "fraud_rule":
        return (
            "Risco alto: cliente recusou o bloqueio"
            if pt
            else "Riesgo alto: cliente rechazó el bloqueo"
        )
    if reason == "fraud_model":
        return "Modelo: revisão" if pt else "Modelo: revisión"
    if not reason:
        return "Motivo não registrado" if pt else "Motivo no registrado"
    return reason


def trail_customer_reason(
    language: str,
    *,
    reason: str,
    status: str,
    band: str,
    case_type: str,
    card_blocked: bool,
) -> str:
    """Customer-safe why-line. No model version, score, or flag name."""
    pt = language == "pt"
    if reason in {"prompt_injection", "injection_detected"} or status == "injection_blocked":
        return "Mensagem bloqueada" if pt else "Mensaje bloqueado"
    if reason == "fraud_model":
        return "Requer revisão de um especialista" if pt else "Requiere revisión de un especialista"
    if reason:
        return handoff_reason_label(
            language,
            reason,
            band=band,
            case_type=case_type,
            synthetic=False,
            card_blocked=card_blocked,
        )
    labels = {
        "pending_explained": "Cobrança pendente" if pt else "Cargo pendiente",
        "reversed_explained": "Cobrança estornada" if pt else "Cargo reversado",
        "merchant_explained": "Explicação do comércio" if pt else "Explicación del comercio",
        "duplicate_explained": "Possível duplicado" if pt else "Posible duplicado",
        "merchant_recognized": "Comércio reconhecido" if pt else "Comercio reconocido",
        "awaiting_block_confirmation": (
            "Confirmação de bloqueio" if pt else "Confirmación de bloqueo"
        ),
    }
    if status in labels:
        return labels[status]
    return "Motivo não registrado" if pt else "Motivo no registrado"


def threshold_crossed(
    band: str, *, fraud_score: float | None, t_low: float, high_value: float
) -> str:
    if band == "high":
        shown = "" if fraud_score is None else f" ({fraud_score:g})"
        return f"fraud_score > {high_value:g}{shown}"
    if band == "review":
        return f"score >= {t_low:.7g}"
    if band == "low":
        return f"score < {t_low:.7g}"
    return "Pending/Reversed"


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _count_text(value: float, language: str) -> str:
    text = f"{value:g}"
    if language == "pt":
        return text.replace(".", ",")
    return text


def _ratio_text(score: float, t_low: float, language: str) -> str | None:
    """Two-decimal score/t_low. A 1.00 rounding keeps the raw >= direction."""
    if t_low <= 0:
        return None
    ratio = (Decimal(str(score)) / Decimal(str(t_low))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    digits = f"{ratio:.2f}"
    if language == "pt":
        digits = digits.replace(".", ",")
    if ratio == Decimal("1.00"):
        sign = "≥" if score >= t_low else "<"
        return f"{sign}{digits}×"
    return f"{digits}×"


def score_line(
    language: str,
    band: str,
    *,
    model_risk_score: float | None,
    fraud_score: float | None,
    t_low: float,
    high_value: float,
) -> str:
    """Agent-facing score sentence. Audit, API enums, and CSV stay on threshold_crossed."""
    lang = _lang(language)
    if band == "high":
        prefix = "Pontuação de fraude" if lang == "pt" else "Puntaje de fraude"
        action = "bloqueio" if lang == "pt" else "bloqueo"
        shown = _finite(fraud_score)
        if shown is None:
            return f"{prefix} > {_count_text(high_value, lang)} → {action}"
        return f"{prefix} {_count_text(shown, lang)} > {_count_text(high_value, lang)} → {action}"
    if band not in {"low", "review"}:
        if lang == "pt":
            return "Pendente/Revertido → explicação por regra"
        return "Pendiente/Revertido → explicación por regla"
    score = _finite(model_risk_score)
    marker = None if score is None else _ratio_text(score, t_low, lang)
    if score is None or marker is None:
        return "Pontuação: —" if lang == "pt" else "Puntaje: —"
    if lang == "pt":
        tail = "acima → revisão" if score >= t_low else "abaixo → automático"
        return f"Pontuação: {marker} limiar · {tail}"
    tail = "encima → revisión" if score >= t_low else "debajo → automático"
    return f"Puntaje: {marker} umbral · {tail}"


def next_step_contest(language: str) -> str:
    if language == "pt":
        return "O cliente rejeitou a explicação automática. Revisar a cobrança. Nenhum crédito foi emitido."
    return (
        "El cliente rechazó la explicación automática. Revisar el cargo. No se emitió un crédito."
    )


MONTHS = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    "pt": ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"),
}

_STATUS = {
    "es": {
        "Approved": "Aprobado",
        "Pending": "Pendiente",
        "Reversed": "Reversado",
        "Declined": "Rechazado",
    },
    "pt": {
        "Approved": "Aprovado",
        "Pending": "Pendente",
        "Reversed": "Estornado",
        "Declined": "Recusado",
    },
}

_UI = {
    "es": {
        "nav_client": "Cliente",
        "nav_agent": "Consola",
        "nav_metrics": "Métricas",
        "lang_name": "Español",
        "tour_open": "¿Cómo funciona?",
        "client_title": "Harbor Desk",
        "client_lede": (
            "Un cargo a la vez. El asistente no mueve dinero: explica, bloquea la tarjeta "
            "solo si usted lo confirma, o pasa el caso a una persona."
        ),
        "charges_title": "Sus cargos, en su hora local",
        "dispute": "No reconozco este cargo",
        "message_placeholder": "Mensaje",
        "send": "Enviar",
        "why": "¿Por qué?",
        "protected": "Protegido",
        "test_badge": "MODO PRUEBA",
        "test_chip": "Prueba",
        "test_arm": "Modo de prueba",
        "test_arm_send": "Activar",
        "test_token": "Token de prueba",
        "agent_title": "Consola del agente",
        "agent_lede": "Cola de casos con el paquete verificado. No hay texto crudo del cliente.",
        "token_placeholder": "Token del agente",
        "load_queue": "Ver cola",
        "queue_empty": "No hay casos en la cola. Abre un caso desde la vista Cliente.",
        "queue_invalid": "Token inválido",
        "queue_failed": "No se pudo leer la cola.",
        "queue_loading": "Cargando la cola…",
        "open_packet": "Abrir paquete",
        "field_band": "Banda",
        "field_score": "Puntaje vs umbral",
        "field_amount": "Monto",
        "field_merchant": "Comercio enmascarado",
        "field_time": "Hora local",
        "field_step": "Siguiente paso",
        "resolve": "Resolver",
        "packet_error": "No se pudo abrir el paquete",
        "resolved": "Resuelto",
        "resolve_error": "No se pudo resolver",
        "no_actions": "ninguna",
        "metrics_title": "Métricas",
        "metrics_lede": (
            "El tablero deja fuera el tráfico de evaluación y el de prueba. Las tasas "
            "de seguridad que necesitan etiquetas viven en el informe fuera de línea."
        ),
        "metrics_loading": "Cargando las métricas…",
        "tile_cases": "Casos",
        "tile_handoff": "Traspaso a persona",
        "tile_containment": "Contención",
        "tile_eval": "Evaluación excluida",
        "tile_test": "Prueba excluida",
        "eval_toggle": (
            "Muestra de demostración (enriquecida en fraude, tasa de riesgo alto cerca de "
            "11 veces la de los datos completos)"
        ),
        "break_it": "Intenta romperlo",
        "no_money": "No se movió dinero",
        "masked_label": "Texto enmascarado",
        "audit_label": "Fila de auditoría",
        "draft_label": "Borrador IA",
        "grounded_ok": "Fundamentado",
        "grounded_bad": "Sin fundamento",
        "send_reply": "Enviar respuesta",
        "reply_sent_label": "Respuesta registrada",
        "health_title": "Salud del sistema",
        "health_p50": "Latencia p50",
        "health_p95": "Latencia p95",
        "health_cost": "Costo medio por llamada",
        "health_calls": "Llamadas",
        "health_empty": "Sin llamadas en esta ventana",
        "trust_title": "Confianza de los datos",
        "sim_title": "Simulador de umbral",
        "sim_split": "Corte",
        "sim_model": "Versión del modelo",
        "sim_default": "Umbral habitual",
        "sim_charges": "Cargos",
        "sim_fraud": "Fraude",
        "sim_high": "Riesgo alto",
        "sim_rule": "Regla",
        "sim_fraud_high": "Fraude en riesgo alto",
        "sim_fraud_rule": "Fraude en la regla",
        "sim_t": "Umbral",
        "sim_n_low": "Bajo",
        "sim_n_review": "Revisión",
        "sim_auto": "Automatización",
        "sim_missed_n": "Fraude no visto",
        "sim_missed_rate": "Tasa de fraude no visto",
        "sim_ci": "Intervalo",
        "sim_wrong": "Cierres indebidos por 10 mil",
        "sim_cost": "Costo por caso",
        "fair_title": "Equidad",
        "fair_country": "País",
        "fair_n": "Casos",
        "fair_low": "Bajo",
        "fair_review": "Revisión",
        "fair_high": "Alto",
        "fair_missed": "Fraude no visto",
    },
    "pt": {
        "nav_client": "Cliente",
        "nav_agent": "Console",
        "nav_metrics": "Métricas",
        "lang_name": "Português",
        "tour_open": "Como funciona?",
        "client_title": "Harbor Desk",
        "client_lede": (
            "Uma cobrança de cada vez. O assistente não move dinheiro: explica, bloqueia o cartão "
            "só se você confirmar, ou passa o caso a uma pessoa."
        ),
        "charges_title": "Suas cobranças, no seu horário local",
        "dispute": "Não reconheço esta cobrança",
        "message_placeholder": "Mensagem",
        "send": "Enviar",
        "why": "Por quê?",
        "protected": "Protegido",
        "test_badge": "MODO TESTE",
        "test_chip": "Teste",
        "test_arm": "Modo de teste",
        "test_arm_send": "Ativar",
        "test_token": "Token de teste",
        "agent_title": "Console do agente",
        "agent_lede": "Fila de casos com o pacote verificado. Não há texto cru do cliente.",
        "token_placeholder": "Token do agente",
        "load_queue": "Ver fila",
        "queue_empty": "Não há casos na fila. Abra um caso na vista Cliente.",
        "queue_invalid": "Token inválido",
        "queue_failed": "Não foi possível ler a fila.",
        "queue_loading": "Carregando a fila…",
        "open_packet": "Abrir pacote",
        "field_band": "Faixa",
        "field_score": "Pontuação vs limiar",
        "field_amount": "Valor",
        "field_merchant": "Comércio mascarado",
        "field_time": "Horário local",
        "field_step": "Próximo passo",
        "resolve": "Resolver",
        "packet_error": "Não foi possível abrir o pacote",
        "resolved": "Resolvido",
        "resolve_error": "Não foi possível resolver",
        "no_actions": "nenhuma",
        "metrics_title": "Métricas",
        "metrics_lede": (
            "O painel deixa de fora o tráfego de avaliação e o de teste. As taxas de "
            "segurança que precisam de rótulos ficam no relatório fora de linha."
        ),
        "metrics_loading": "Carregando as métricas…",
        "tile_cases": "Casos",
        "tile_handoff": "Repasse a uma pessoa",
        "tile_containment": "Contenção",
        "tile_eval": "Avaliação excluída",
        "tile_test": "Teste excluído",
        "eval_toggle": (
            "Amostra de demonstração (enriquecida em fraude, taxa de risco alto cerca de "
            "11 vezes a dos dados completos)"
        ),
        "break_it": "Tente quebrá-lo",
        "no_money": "Nenhum dinheiro foi movido",
        "masked_label": "Texto mascarado",
        "audit_label": "Linha de auditoria",
        "draft_label": "Rascunho IA",
        "grounded_ok": "Fundamentado",
        "grounded_bad": "Sem fundamento",
        "send_reply": "Enviar resposta",
        "reply_sent_label": "Resposta registrada",
        "health_title": "Saúde do sistema",
        "health_p50": "Latência p50",
        "health_p95": "Latência p95",
        "health_cost": "Custo médio por chamada",
        "health_calls": "Chamadas",
        "health_empty": "Sem chamadas nesta janela",
        "trust_title": "Confiança dos dados",
        "sim_title": "Simulador de limiar",
        "sim_split": "Corte",
        "sim_model": "Versão do modelo",
        "sim_default": "Limiar habitual",
        "sim_charges": "Cobranças",
        "sim_fraud": "Fraude",
        "sim_high": "Risco alto",
        "sim_rule": "Regra",
        "sim_fraud_high": "Fraude no risco alto",
        "sim_fraud_rule": "Fraude na regra",
        "sim_t": "Limiar",
        "sim_n_low": "Baixo",
        "sim_n_review": "Revisão",
        "sim_auto": "Automação",
        "sim_missed_n": "Fraude não vista",
        "sim_missed_rate": "Taxa de fraude não vista",
        "sim_ci": "Intervalo",
        "sim_wrong": "Fechos indevidos por 10 mil",
        "sim_cost": "Custo por caso",
        "fair_title": "Equidade",
        "fair_country": "País",
        "fair_n": "Casos",
        "fair_low": "Baixo",
        "fair_review": "Revisão",
        "fair_high": "Alto",
        "fair_missed": "Fraude não vista",
    },
}


def _lang(language: str) -> str:
    return "pt" if language == "pt" else "es"


def months(language: str) -> tuple[str, ...]:
    return MONTHS[_lang(language)]


def transaction_status_label(language: str, status: str) -> str:
    return _STATUS[_lang(language)].get(status, status)


def persona_note(language: str, persona_id: str, *, postgres: bool) -> str:
    """Chip text. English source notes are not shown."""
    lang = _lang(language)
    if postgres:
        if persona_id == "lucia":
            return (
                "Cliente dos dados do desafio, cobrança duplicada"
                if lang == "pt"
                else "Cliente de los datos del desafío, cargo duplicado"
            )
        return (
            "Cliente dos dados do desafio" if lang == "pt" else "Cliente de los datos del desafío"
        )
    if persona_id == "teo":
        return (
            "Pessoa sintética. MX não é a Cidade do México."
            if lang == "pt"
            else "Persona sintética. MX no es Ciudad de México."
        )
    if persona_id == "lucia":
        return (
            "Pessoa sintética, cobrança duplicada"
            if lang == "pt"
            else "Persona sintética, cargo duplicado"
        )
    return "Pessoa sintética" if lang == "pt" else "Persona sintética"


def persona_label(language: str, persona_id: str, fallback: str) -> str:
    labels = {
        "camilo": {"es": "Camilo · Colombia", "pt": "Camilo · Colômbia"},
        "maria": {"es": "María · Ciudad de México", "pt": "María · Cidade do México"},
    }
    row = labels.get(persona_id)
    if row is None:
        return fallback
    return row[_lang(language)]


def localize_stored_merchant(language: str, stored: str) -> str:
    """Rewrite a packet fallback that was saved in the other language."""
    text = (stored or "").strip()
    lang = _lang(language)
    blanks = {"es": "Comercio no identificado", "pt": "Comércio não identificado"}
    if text in blanks.values():
        return blanks[lang]
    lowered = text.lower()
    for prefix in ("categoría ", "categoria "):
        if lowered.startswith(prefix):
            return merchant_label(lang, "", text[len(prefix) :], "")
    if lowered.startswith("tipo "):
        return merchant_label(lang, "", "", text[5:])
    return text


def display_next_step(language: str, reason: str, *, card_blocked: bool, stored: str) -> str:
    if reason == "fraud_rule" and card_blocked:
        return next_step_block(language)
    if reason == "customer_contests_rule_answer":
        return next_step_contest(language)
    if reason in {"fraud_model", "fraud_rule", "customer_requested_human"}:
        return next_step_review(language)
    return stored


def ui_copy(language: str) -> dict[str, object]:
    lang = _lang(language)
    payload: dict[str, object] = dict(_UI[lang])
    payload["status"] = dict(_STATUS[lang])
    payload["types"] = dict(_TRANSACTION_TYPES[lang])
    payload["categories"] = dict(_CATEGORIES[lang])
    payload["bands"] = dict(_BANDS[lang])
    payload["actions"] = dict(_ACTION_PHRASES[lang])
    payload["decisions"] = dict(_DECISIONS[lang])
    payload["months"] = list(MONTHS[lang])
    return payload


def ui_catalog() -> dict[str, dict[str, object]]:
    return {"es": ui_copy("es"), "pt": ui_copy("pt")}


def catalog_script() -> str:
    """ES and PT strings for the pages. Generated from ui_catalog(); do not hand-edit."""
    payload = json.dumps(ui_catalog(), ensure_ascii=False, separators=(",", ":"))
    payload = (
        payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )
    return (
        f"// Generated from app.i18n.ui_catalog. Do not edit.\nglobalThis.HD_CATALOG={payload};\n"
    )


def write_catalog_script(path: Path | None = None) -> Path:
    from app.paths import project_root

    destination = path or (project_root() / "static" / "js" / "catalog.js")
    text = catalog_script()
    current = destination.read_text(encoding="utf-8") if destination.exists() else ""
    if current != text:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    return destination


_METRICS_TEXT = {
    "es": {
        "not defined": "no definido",
        "offline": "fuera de línea",
        "Requires eval.case_labels. This console role cannot read the eval schema.": (
            "Requiere las etiquetas de evaluación. Este rol no puede leer ese esquema."
        ),
        "Rates use closed cases. Open cases are counted as still_open and are not mixed in.": (
            "Las tasas usan casos cerrados. Los casos abiertos se cuentan aparte y no se mezclan."
        ),
        "n < 30 is not reliable": "n < 30 no es confiable",
        "PROJECTION": "PROYECCIÓN",
        "PROJECTION: wage rates assumed. The safe-automated numerator is offline.": (
            "PROYECCIÓN: salarios supuestos. El numerador de automatización segura está fuera de línea."
        ),
        "Portuguese rows are machine-translated test cases, not production traffic.": (
            "Las filas en portugués son casos de prueba traducidos, no tráfico real."
        ),
    },
    "pt": {
        "not defined": "não definido",
        "offline": "fora de linha",
        "Requires eval.case_labels. This console role cannot read the eval schema.": (
            "Requer os rótulos de avaliação. Este papel não pode ler esse esquema."
        ),
        "Rates use closed cases. Open cases are counted as still_open and are not mixed in.": (
            "As taxas usam casos fechados. Os casos abertos são contados à parte e não se misturam."
        ),
        "n < 30 is not reliable": "n < 30 não é confiável",
        "PROJECTION": "PROJEÇÃO",
        "PROJECTION: wage rates assumed. The safe-automated numerator is offline.": (
            "PROJEÇÃO: salários supostos. O numerador de automação segura está fora de linha."
        ),
        "Portuguese rows are machine-translated test cases, not production traffic.": (
            "As linhas em português são casos de teste traduzidos, não tráfego real."
        ),
    },
}


def localize_metrics(payload: dict[str, object], language: str) -> dict[str, object]:
    """Translate the sentences in a metrics document. Keys stay stable."""
    table = _METRICS_TEXT[_lang(language)]

    def walk(value: object) -> object:
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str) and value in table:
            return table[value]
        return value

    walked = walk(payload)
    assert isinstance(walked, dict)
    return walked
