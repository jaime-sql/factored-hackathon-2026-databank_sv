"""Customer-facing agent copy in Spanish and Portuguese."""

from __future__ import annotations

_COPY: dict[str, dict[str, str]] = {
    "es": {
        "agent_label": "Agente IA",
        "guided_note": "Modo guiado",
        "thinking": "Pensando…",
        "start_buscar_cargos": "Buscando sus cargos…",
        "start_calcular_riesgo": "Calculando el riesgo…",
        "start_explicar_estado": "Revisando el estado del cargo…",
        "start_pedir_confirmacion_bloqueo": "Preparando la confirmación…",
        "start_pasar_a_humano": "Pasando el caso a una persona…",
        "found_one": "Encontré 1 cargo de {merchant} · {date} · {amount}",
        "found_many": "Encontré {n} cargos posibles",
        "found_none": "No encontré cargos con esos datos",
        "risk": "Riesgo: {band}",
        "explained": "Expliqué el estado: {status}",
        "confirm_asked": "Pedí su confirmación antes de bloquear",
        "handed_off": "Pasé el caso a una persona",
        "guardrail": "Protegido: instrucción ignorada",
        "step_failed": "No pude completar este paso",
        "pick_one": "Encontré varios cargos posibles. ¿Cuál de estos es?",
        "none_found": "No encontré ese cargo. Elija uno de su lista o deme el monto o la fecha.",
        "confirm_block": "Confirmo el bloqueo",
        "decline_block": "No, solo revisar",
        "band_pending": "sin riesgo de fraude, solo el estado",
        "explained_low": "Le expliqué el cargo: riesgo bajo",
        "high_status_asked": "Riesgo alto: pedí su confirmación antes de bloquear",
        "high_pending": (
            "Ese cargo está pendiente, todavía no se ha cobrado. Además, lo marcamos como "
            "riesgo alto. ¿Bloqueamos tu tarjeta?"
        ),
        "high_reversed": (
            "Ese cargo fue revertido, el monto ya volvió. Además, lo marcamos como riesgo "
            "alto. ¿Bloqueamos tu tarjeta?"
        ),
    },
    "pt": {
        "agent_label": "Agente IA",
        "guided_note": "Modo guiado",
        "thinking": "Pensando…",
        "start_buscar_cargos": "Procurando suas cobranças…",
        "start_calcular_riesgo": "Calculando o risco…",
        "start_explicar_estado": "Verificando o status da cobrança…",
        "start_pedir_confirmacion_bloqueo": "Preparando a confirmação…",
        "start_pasar_a_humano": "Passando o caso para uma pessoa…",
        "found_one": "Encontrei 1 cobrança de {merchant} · {date} · {amount}",
        "found_many": "Encontrei {n} cobranças possíveis",
        "found_none": "Não encontrei cobranças com esses dados",
        "risk": "Risco: {band}",
        "explained": "Expliquei o status: {status}",
        "confirm_asked": "Pedi sua confirmação antes de bloquear",
        "handed_off": "Passei o caso para uma pessoa",
        "guardrail": "Protegido: instrução ignorada",
        "step_failed": "Não consegui concluir esta etapa",
        "pick_one": "Encontrei várias cobranças possíveis. Qual destas é?",
        "none_found": (
            "Não encontrei essa cobrança. Escolha uma da sua lista ou me diga o valor ou a data."
        ),
        "confirm_block": "Confirmo o bloqueio",
        "decline_block": "Não, só revisar",
        "band_pending": "sem risco de fraude, só o status",
        "explained_low": "Expliquei a cobrança: risco baixo",
        "high_status_asked": "Risco alto: pedi sua confirmação antes de bloquear",
        "high_pending": (
            "Essa cobrança está pendente, ainda não foi cobrada. Além disso, marcamos como "
            "risco alto. Bloqueamos seu cartão?"
        ),
        "high_reversed": (
            "Essa cobrança foi estornada, o valor já voltou. Além disso, marcamos como risco "
            "alto. Bloqueamos seu cartão?"
        ),
    },
}


def agent_copy(language: str, key: str, **values: object) -> str:
    table = _COPY["pt" if language == "pt" else "es"]
    text = table.get(key, _COPY["es"].get(key, key))
    return text.format(**values) if values else text


def agent_catalog() -> dict[str, dict[str, str]]:
    return {lang: dict(rows) for lang, rows in _COPY.items()}
