"""Spanish (LATAM) and Portuguese templates.

Portuguese strings are machine-translated and must be reported as language=pt,
never as production traffic from Portuguese-speaking customers. The bank's
customers in this slice are in MX, CO, and AR.
"""

from __future__ import annotations

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


def money(amount: float, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def merchant_label(language: str, name: str, category: str, transaction_type: str) -> str:
    """Readable merchant for replies. Empty when name, category, and type are blank."""
    cleaned_name = (name or "").strip()
    if cleaned_name:
        return cleaned_name
    cleaned_category = (category or "").strip()
    if cleaned_category:
        if language == "pt":
            return f"categoria {cleaned_category}"
        return f"categoría {cleaned_category}"
    cleaned_type = (transaction_type or "").strip()
    if cleaned_type:
        if language == "pt":
            return f"tipo {cleaned_type}"
        return f"tipo {cleaned_type}"
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
            return f"A cobrança da categoria {(category or '').strip()} ({amount})"
        if (
            not (name or "").strip()
            and not (category or "").strip()
            and (transaction_type or "").strip()
        ):
            return f"A cobrança do tipo {(transaction_type or '').strip()} ({amount})"
        if label:
            return f"A cobrança de {label} ({amount})"
        return f"A cobrança ({amount})"
    if not (name or "").strip() and (category or "").strip():
        return f"El cargo de la categoría {(category or '').strip()} ({amount})"
    if (
        not (name or "").strip()
        and not (category or "").strip()
        and (transaction_type or "").strip()
    ):
        return f"El cargo de tipo {(transaction_type or '').strip()} ({amount})"
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
            head = f"Há um possível duplicado SINTÉTICO da categoria {(category or '').strip()} ({amount})"
        elif label:
            head = f"Há um possível duplicado SINTÉTICO de {label} ({amount})"
        else:
            head = f"Há um possível duplicado SINTÉTICO ({amount})"
        return (
            f"{head}: {when} e {other_when}. "
            "Este par vem do cenário de teste synthetic_duplicates (is_synthetic=1), não de um duplicado real. "
            "Se reconhece o comércio, fechamos. Se não, uma pessoa revisa. Nenhum dinheiro foi movido."
        )
    if not (merchant or "").strip() and (category or "").strip():
        head = f"Hay un posible duplicado SINTÉTICO de la categoría {(category or '').strip()} ({amount})"
    elif label:
        head = f"Hay un posible duplicado SINTÉTICO de {label} ({amount})"
    else:
        head = f"Hay un posible duplicado SINTÉTICO ({amount})"
    return (
        f"{head}: {when} y {other_when}. "
        "Este par sale del escenario de prueba synthetic_duplicates (is_synthetic=1), no de un duplicado real. "
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


_FALLBACK_MERCHANT_PREFIXES = (
    "categoría ",
    "categoria ",
    "tipo ",
)
_FALLBACK_MERCHANT_EXACT = {
    "comercio no identificado",
    "comércio não identificado",
}


def mask_merchant(label: str) -> str:
    """Hide a real merchant name. Category and type fallbacks stay readable."""
    text = (label or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in _FALLBACK_MERCHANT_EXACT or lowered.startswith(_FALLBACK_MERCHANT_PREFIXES):
        return text
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


def next_step_contest(language: str) -> str:
    if language == "pt":
        return "O cliente rejeitou a explicação automática. Revisar a cobrança. Nenhum crédito foi emitido."
    return (
        "El cliente rechazó la explicación automática. Revisar el cargo. No se emitió un crédito."
    )
