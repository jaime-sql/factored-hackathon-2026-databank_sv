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


def reply_pending(language: str, merchant: str, amount: str, when: str) -> str:
    if language == "pt":
        body = (
            f"A cobrança de {merchant} ({amount}) em {when} ainda está pendente. "
            "Ainda não é definitiva, então não há o que contestar agora. "
            "Nenhum dinheiro foi movido por este assistente."
        )
    else:
        body = (
            f"El cargo de {merchant} ({amount}) del {when} sigue pendiente. "
            "Todavía no es definitivo, así que no hay nada que disputar. "
            "Este asistente no movió dinero."
        )
    return body + "\n\n" + _contest_footer(language)


def reply_reversed(language: str, merchant: str, amount: str, when: str) -> str:
    if language == "pt":
        body = (
            f"A cobrança de {merchant} ({amount}) em {when} já foi estornada. "
            "O valor já voltou. Este assistente não moveu dinheiro."
        )
    else:
        body = (
            f"El cargo de {merchant} ({amount}) del {when} ya fue reversado. "
            "El dinero ya regresó. Este asistente no movió dinero."
        )
    return body + "\n\n" + _contest_footer(language)


def reply_high(language: str, merchant: str, amount: str, when: str) -> str:
    if language == "pt":
        return (
            f"A cobrança de {merchant} ({amount}) em {when} supera a regra de risco "
            "(pontuação de fraude maior que 30). Podemos bloquear o cartão. "
            "O bloqueio só acontece se você confirmar. Nenhum dinheiro foi movido."
        )
    return (
        f"El cargo de {merchant} ({amount}) del {when} supera la regla de riesgo "
        "(puntaje de fraude mayor que 30). Podemos bloquear la tarjeta. "
        "El bloqueo solo se hace si usted lo confirma. No se movió dinero."
    )


def reply_low(
    language: str, merchant: str, category: str, city: str, when: str, amount: str
) -> str:
    if language == "pt":
        return (
            f"Encontrei {merchant} ({category}) em {city}, {when}, por {amount}. "
            "Está no seu histórico. Se agora reconhece o comércio, fechamos o caso. "
            "Se não, uma pessoa revisa. Nenhum dinheiro foi movido."
        )
    return (
        f"Encontré {merchant} ({category}) en {city}, el {when}, por {amount}. "
        "Está en su historial. Si ahora reconoce el comercio, cerramos el caso. "
        "Si no, una persona lo revisa. No se movió dinero."
    )


def reply_review(language: str, merchant: str, amount: str) -> str:
    if language == "pt":
        return (
            f"A cobrança de {merchant} ({amount}) precisa de uma pessoa. "
            "Não oferecemos bloqueio do cartão neste caso. Nenhum dinheiro foi movido."
        )
    return (
        f"El cargo de {merchant} ({amount}) necesita una persona. "
        "No ofrecemos bloquear la tarjeta en este caso. No se movió dinero."
    )


def reply_duplicate(
    language: str,
    merchant: str,
    amount: str,
    when: str,
    other_when: str,
) -> str:
    if language == "pt":
        return (
            f"Há um possível duplicado SINTÉTICO de {merchant} ({amount}): {when} e {other_when}. "
            "Este par vem do cenário de teste synthetic_duplicates (is_synthetic=1), não de um duplicado real. "
            "Se reconhece o comércio, fechamos. Se não, uma pessoa revisa. Nenhum dinheiro foi movido."
        )
    return (
        f"Hay un posible duplicado SINTÉTICO de {merchant} ({amount}): {when} y {other_when}. "
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
        return "Só posso ajudar com uma cobrança da sua lista. Descreva o cargo, sem instruções para o assistente."
    return "Solo puedo ayudar con un cargo de su lista. Describa el cargo, sin instrucciones para el asistente."


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


def next_step_contest(language: str) -> str:
    if language == "pt":
        return "O cliente rejeitou a explicação automática. Revisar a cobrança. Nenhum crédito foi emitido."
    return (
        "El cliente rechazó la explicación automática. Revisar el cargo. No se emitió un crédito."
    )
