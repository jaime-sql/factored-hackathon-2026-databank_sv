"""Transaction-level dispute intake.

Routing order, from the vendored thresholds:
1. fraud_score > 30 is HIGH for every status, including Pending and Reversed.
2. Otherwise Pending and Reversed get the fixed explanation.
3. A charge with no fraud_features row is REVIEW, never LOW.
   A SYN_* pair inherits its source transaction's features before that check.
4. Otherwise the learned model returns REVIEW or LOW.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.bank.models import Customer, Transaction
from app.bank.repository import BankRepository, synthetic_pair_sibling
from app.config import Settings
from app.errors import APIError
from app.guardrails.injection import detect_injection
from app.guardrails.pii import redact
from app.handoff.packet import (
    ActionTaken,
    HandoffPacket,
    TransactionFacts,
    TriageInfo,
)
from app.i18n import (
    confirm_block_label,
    contest_label,
    decline_block_label,
    detect_language,
    dispute_label,
    money,
    next_step_block,
    next_step_contest,
    next_step_review,
    recognize_label,
    reply_block_failed,
    reply_blocked,
    reply_clarify,
    reply_contested,
    reply_declined_block,
    reply_dispute_opened,
    reply_duplicate,
    reply_high,
    reply_injection,
    reply_low,
    reply_pending,
    reply_permission,
    reply_recognized,
    reply_reversed,
    reply_review,
)
from app.ids import new_case_id, new_id
from app.ops.store import OpsStore
from app.thresholds_loader import ThresholdSource, preliminary_route
from app.timeutil import present_time
from app.triage_model import (
    FALLBACK_VERSION,
    RULE_VERSION,
    LightGBMTriage,
    TriageModel,
    TriageScore,
    fallback_score,
)

logger = logging.getLogger("app.cases")

_COUNTRY = {
    "AR": "AR",
    "ARGENTINA": "AR",
    "CO": "CO",
    "COLOMBIA": "CO",
    "MX": "MX",
    "MEXICO": "MX",
    "MÉXICO": "MX",
}

_ALLOWED: dict[str, set[str]] = {
    "awaiting_block_confirmation": {"confirm_block", "decline_block"},
    "rule_explained": {"contest"},
    "merchant_explained": {"recognize", "open_dispute"},
    "duplicate_explained": {"recognize", "open_dispute"},
    "handed_off": set(),
    "closed": set(),
    "clarifying": set(),
}


def country_code(value: str | None) -> str:
    if not value:
        return ""
    return _COUNTRY.get(value.strip().upper(), "")


@dataclass
class ActionButton:
    id: str
    label: str
    emphasis: str = "secondary"


@dataclass
class CaseResult:
    case_id: str
    reply: str
    language: str
    case_type: str
    band: str
    actions: list[ActionButton]
    model_risk_score: float | None
    state: str
    eval_run_id: str | None
    case_source: str | None
    guardrail_flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "reply": self.reply,
            "language": self.language,
            "case_type": self.case_type,
            "band": self.band,
            "actions": [action.__dict__ for action in self.actions],
            "model_risk_score": self.model_risk_score,
            "state": self.state,
            "eval_run_id": self.eval_run_id,
            "case_source": self.case_source,
            "money_movement": "none",
        }


class Engine:
    def __init__(
        self,
        bank: BankRepository,
        ops: OpsStore,
        thresholds: ThresholdSource,
        settings: Settings,
        triage: TriageModel | None = None,
    ) -> None:
        self.bank = bank
        self.ops = ops
        self.thresholds = thresholds
        self.settings = settings
        self.triage = triage or LightGBMTriage()

    def open_case(
        self,
        customer_key: str,
        transaction_key: str | None,
        message: str,
        language: str | None,
        eval_run_id: str | None,
        case_source: str | None,
    ) -> CaseResult:
        lang = detect_language(message or "", language)
        flags: list[str] = []
        redacted, changed = _redact(message or "")
        if changed:
            flags.append("pii_redacted_input")
        if detect_injection(redacted).blocked:
            return self._injection(customer_key, lang, flags, eval_run_id, case_source)
        if not transaction_key:
            return self._clarify(customer_key, lang, flags, eval_run_id, case_source)
        customer = self.bank.get_customer(customer_key)
        if customer is None:
            raise APIError(404, "not_found", "Customer not found")
        tx = self.bank.get_transaction(customer_key, transaction_key)
        if tx is None:
            raise APIError(404, "not_found", "Charge not found")
        features = self.bank.get_features(customer_key, transaction_key)
        duplicate = self.bank.get_duplicate(customer_key, transaction_key)
        return self._route(customer, tx, features, duplicate, lang, flags, eval_run_id, case_source)

    def act(self, customer_key: str, case_id: str, action: str) -> CaseResult:
        case = self._own_case(customer_key, case_id)
        allowed = _ALLOWED.get(str(case["state"]), set())
        if action not in allowed:
            self._event(case_id, "tool", action, {"verification_status": "failed"}, "failed")
            flags = list(self._flags(case_id))
            flags.append("unauthorized_access")
            self._rewrite_flags(case, flags)
            lang = str(case["language"])
            raise APIError(403, "permission_denied", reply_permission(lang))
        if action == "confirm_block":
            return self._confirm_block(case)
        if action == "decline_block":
            return self._decline_block(case)
        if action == "contest":
            return self._contest(case)
        if action == "recognize":
            return self._recognize(case)
        if action == "open_dispute":
            return self._dispute(case)
        raise APIError(403, "permission_denied", reply_permission(str(case["language"])))

    def _route(
        self,
        customer: Customer,
        tx: Transaction,
        features: dict[str, object] | None,
        duplicate: Any,
        lang: str,
        flags: list[str],
        eval_run_id: str | None,
        case_source: str | None,
    ) -> CaseResult:
        if (
            features is None
            and synthetic_pair_sibling(tx.transaction_key)
            and duplicate is not None
            and duplicate.source_transaction_key
        ):
            # Demo choice: SYN_* is absent from fraud_features, so score the source row.
            features = self.bank.get_features(
                customer.customer_key, str(duplicate.source_transaction_key)
            )
        config = self.thresholds.get()
        route = preliminary_route(tx.fraud_score, tx.transaction_status, config)
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, lang)
        amount = money(tx.amount, tx.currency)
        scored: TriageScore | None = None
        if route == "high":
            band = "high"
            version = RULE_VERSION
            case_type = "triage"
        elif route == "pending":
            band = "out_of_scope"
            version = RULE_VERSION
            case_type = "pending"
        elif route == "reversed":
            band = "out_of_scope"
            version = RULE_VERSION
            case_type = "reversed"
        elif features is None:
            scored = fallback_score(
                {"fraud_score": tx.fraud_score, "transaction_status": tx.transaction_status},
                config,
            )
            band = "review"
            version = FALLBACK_VERSION
            flags.append("fallback_used")
            case_type = "duplicate_synthetic" if duplicate is not None else "triage"
        else:
            payload = dict(features)
            payload["transaction_key"] = tx.transaction_key
            payload["transaction_status"] = tx.transaction_status
            payload["fraud_score"] = tx.fraud_score
            try:
                scored = self.triage.score(payload, config)
            except Exception:
                logger.info("triage_fallback", extra={"transaction_key": tx.transaction_key})
                scored = fallback_score(payload, config)
            if scored.used_fallback:
                flags.append("fallback_used")
            if scored.band == "high":
                flags.append("triage_band_mismatch")
                band = "review"
                version = scored.model_version
            elif scored.band == "low" and scored.used_fallback:
                flags.append("triage_band_mismatch")
                band = "review"
                version = FALLBACK_VERSION
            else:
                band = scored.band if scored.band in {"low", "review"} else "review"
                version = scored.model_version
            case_type = "duplicate_synthetic" if duplicate is not None else "triage"
        prob = (
            None
            if scored is None or route in {"high", "pending", "reversed"}
            else scored.model_risk_score
        )
        if route in {"pending", "reversed"}:
            prob = None
        case_id = new_case_id()
        now = datetime.now(UTC)
        state, decision, closed, automation, reason, status, actions, reply = self._opening(
            route, band, case_type, lang, tx, amount, shown["label"], duplicate, customer, case_id
        )
        is_eval = bool(eval_run_id or case_source)
        audit_id = new_case_id()
        self.ops.insert_case(
            {
                "case_id": case_id,
                "customer_key": customer.customer_key,
                "transaction_key": tx.transaction_key,
                "state": state,
                "language": lang,
                "case_type": case_type,
                "created_at": now,
                "updated_at": now,
                "closed_at": closed,
                "latest_audit_id": audit_id,
                "is_eval_case": is_eval,
                "eval_run_id": eval_run_id,
                "case_source": case_source,
            }
        )
        self._audit(
            case_id=case_id,
            audit_id=audit_id,
            supersedes=None,
            case_type=case_type,
            customer=customer,
            status=status,
            created=now,
            closed=closed,
            decision=decision,
            automation=automation,
            reason=reason,
            packet_complete=None,
            lang=lang,
            version=version,
            fraud_score=tx.fraud_score,
            prob=prob,
            flags=flags,
            is_eval=is_eval,
            eval_run_id=eval_run_id,
            case_source=case_source,
        )
        self._event(
            case_id, "step", "route", {"band": band, "case_type": case_type}, "not_applicable"
        )
        if decision == "handoff":
            self._deliver_handoff(
                case_id,
                customer,
                tx,
                shown,
                band,
                tx.fraud_score,
                prob,
                version,
                lang,
                ["Reviewed by a person. No credit was issued."],
                [],
                next_step_review(lang),
                duplicate is not None,
                reason or "fraud_model",
                flags,
            )
        return CaseResult(
            case_id,
            reply,
            lang,
            case_type,
            band,
            actions,
            prob,
            state,
            eval_run_id,
            case_source,
            flags,
        )

    def _opening(
        self,
        route: str,
        band: str,
        case_type: str,
        lang: str,
        tx: Transaction,
        amount: str,
        when: str,
        duplicate: Any,
        customer: Customer,
        case_id: str,
    ) -> tuple[Any, ...]:
        del case_id
        if route == "high" or band == "high":
            return (
                "awaiting_block_confirmation",
                None,
                None,
                True,
                None,
                "awaiting_block_confirmation",
                [
                    ActionButton("confirm_block", confirm_block_label(lang), "primary"),
                    ActionButton("decline_block", decline_block_label(lang)),
                ],
                reply_high(lang, tx.merchant_name, amount, when),
            )
        if route == "pending":
            return (
                "rule_explained",
                "auto_resolved",
                datetime.now(UTC),
                True,
                None,
                "pending_explained",
                [ActionButton("contest", contest_label(lang), "primary")],
                reply_pending(lang, tx.merchant_name, amount, when),
            )
        if route == "reversed":
            return (
                "rule_explained",
                "auto_resolved",
                datetime.now(UTC),
                True,
                None,
                "reversed_explained",
                [ActionButton("contest", contest_label(lang), "primary")],
                reply_reversed(lang, tx.merchant_name, amount, when),
            )
        if case_type == "duplicate_synthetic" and band == "low":
            other_when = when
            if duplicate is not None and duplicate.other_ts_utc is not None:
                other_when = present_time(
                    duplicate.other_ts_utc, customer.tz, customer.customer_country, lang
                )["label"]
            other = other_when
            return (
                "duplicate_explained",
                None,
                None,
                True,
                None,
                "duplicate_explained",
                [
                    ActionButton("recognize", recognize_label(lang)),
                    ActionButton("open_dispute", dispute_label(lang), "primary"),
                ],
                reply_duplicate(lang, tx.merchant_name, amount, when, other),
            )
        if band == "low":
            return (
                "merchant_explained",
                None,
                None,
                True,
                None,
                "merchant_explained",
                [
                    ActionButton("recognize", recognize_label(lang)),
                    ActionButton("open_dispute", dispute_label(lang), "primary"),
                ],
                reply_low(
                    lang, tx.merchant_name, tx.merchant_category, tx.transaction_city, when, amount
                ),
            )
        return (
            "handed_off",
            "handoff",
            datetime.now(UTC),
            False,
            "fraud_model",
            "handed_off",
            [],
            reply_review(lang, tx.merchant_name, amount),
        )

    def _confirm_block(self, case: dict[str, Any]) -> CaseResult:
        case_id = str(case["case_id"])
        lang = str(case["language"])
        customer_key = str(case["customer_key"])
        tx = self._tx(case)
        customer = self._customer(customer_key)
        self.ops.insert_confirmation(new_case_id(), case_id, "card_block")
        if not self.ops.has_confirmation(case_id, "card_block"):
            raise APIError(403, "permission_denied", reply_permission(lang))
        block_id = new_case_id()
        self.ops.insert_block(
            {
                "block_id": block_id,
                "case_id": case_id,
                "customer_key": customer_key,
                "product_key": tx.product_key,
                "transaction_key": tx.transaction_key,
                "status": "blocked",
            }
        )
        readback = self.ops.get_block(case_id)
        verified = (
            readback is not None
            and readback.get("product_key") == tx.product_key
            and readback.get("status") == "blocked"
            and readback.get("customer_key") == customer_key
        )
        self._event(
            case_id,
            "tool",
            "block_card",
            {"product_key": tx.product_key},
            "verified" if verified else "failed",
        )
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, lang)
        flags = self._flags(case_id)
        if not verified:
            flags.append("tool_failure")
            reply = reply_block_failed(lang, case_id)
            actions_taken = [ActionTaken(name="block_card", verification_status="failed")]
            step = next_step_review(lang)
        else:
            reply = reply_blocked(lang, case_id)
            actions_taken = [ActionTaken(name="block_card", verification_status="verified")]
            step = next_step_block(lang)
        self._close_handoff(
            case,
            tx,
            customer,
            shown,
            "high",
            RULE_VERSION,
            None,
            "fraud_rule",
            "blocked_and_handed_off" if verified else "block_unverified_handed_off",
            reply,
            step,
            actions_taken,
            flags,
            [],
        )
        return self._result(case_id, reply, "triage", "high", [], None)

    def _decline_block(self, case: dict[str, Any]) -> CaseResult:
        tx = self._tx(case)
        customer = self._customer(str(case["customer_key"]))
        lang = str(case["language"])
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, lang)
        reply = reply_declined_block(lang, str(case["case_id"]))
        self._close_handoff(
            case,
            tx,
            customer,
            shown,
            "high",
            RULE_VERSION,
            None,
            "fraud_rule",
            "declined_block_handed_off",
            reply,
            next_step_review(lang),
            [ActionTaken(name="decline_block", verification_status="not_applicable")],
            self._flags(case),
            ["Customer declined the card block."],
        )
        return self._result(str(case["case_id"]), reply, "triage", "high", [], None)

    def _contest(self, case: dict[str, Any]) -> CaseResult:
        tx = self._tx(case)
        customer = self._customer(str(case["customer_key"]))
        lang = str(case["language"])
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, lang)
        reply = reply_contested(lang, str(case["case_id"]))
        self._close_handoff(
            case,
            tx,
            customer,
            shown,
            "out_of_scope",
            RULE_VERSION,
            None,
            "customer_contests_rule_answer",
            "contested_rule_handed_off",
            reply,
            next_step_contest(lang),
            [ActionTaken(name="contest", verification_status="not_applicable")],
            self._flags(case),
            ["Customer rejected the automatic explanation."],
        )
        case_type = str(case["case_type"] or "pending")
        return self._result(str(case["case_id"]), reply, case_type, "out_of_scope", [], None)

    def _recognize(self, case: dict[str, Any]) -> CaseResult:
        lang = str(case["language"])
        reply = reply_recognized(lang)
        now = datetime.now(UTC)
        self.ops.update_case(
            str(case["case_id"]),
            {"state": "closed", "updated_at": now, "closed_at": now},
        )
        self._supersede(
            case,
            decision="auto_resolved",
            closed=now,
            status="merchant_recognized",
            reason=None,
            packet_complete=None,
            state_case_type=str(case["case_type"]),
        )
        self._event(str(case["case_id"]), "step", "recognize", {}, "not_applicable")
        return self._result(
            str(case["case_id"]),
            reply,
            str(case["case_type"]),
            "low",
            [],
            None,
        )

    def _dispute(self, case: dict[str, Any]) -> CaseResult:
        tx = self._tx(case)
        customer = self._customer(str(case["customer_key"]))
        lang = str(case["language"])
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, lang)
        reply = reply_dispute_opened(lang, str(case["case_id"]))
        duplicate = self.bank.get_duplicate(customer.customer_key, tx.transaction_key)
        self._close_handoff(
            case,
            tx,
            customer,
            shown,
            "low",
            str(self._version(case)),
            self._prob(case),
            "customer_requested_human",
            "dispute_queued",
            reply,
            next_step_review(lang),
            [ActionTaken(name="open_dispute", verification_status="not_applicable")],
            self._flags(case),
            [],
            synthetic=duplicate is not None,
        )
        return self._result(
            str(case["case_id"]), reply, str(case["case_type"]), "low", [], self._prob(case)
        )

    def _close_handoff(
        self,
        case: dict[str, Any],
        tx: Transaction,
        customer: Customer,
        shown: dict[str, str],
        band: str,
        version: str,
        prob: float | None,
        reason: str,
        status: str,
        reply: str,
        step: str,
        actions_taken: list[ActionTaken],
        flags: list[str],
        extra_facts: list[str],
        synthetic: bool = False,
    ) -> None:
        del reply
        case_id = str(case["case_id"])
        now = datetime.now(UTC)
        packet = self._packet(
            case_id,
            customer,
            tx,
            shown,
            band,
            tx.fraud_score,
            prob,
            version,
            str(case["language"]),
            extra_facts,
            actions_taken,
            step,
            synthetic,
        )
        self._store_handoff(case_id, packet, reason)
        self.ops.update_case(
            case_id,
            {
                "state": "handed_off",
                "updated_at": now,
                "closed_at": now,
                "case_type": case["case_type"],
            },
        )
        case["state"] = "handed_off"
        self._supersede(
            case,
            decision="handoff",
            closed=now,
            status=status,
            reason=reason,
            packet_complete=True,
            flags=flags,
            prob=prob,
            version=version,
        )

    def _deliver_handoff(
        self,
        case_id: str,
        customer: Customer,
        tx: Transaction,
        shown: dict[str, str],
        band: str,
        fraud_score: float | None,
        prob: float | None,
        version: str,
        lang: str,
        facts: list[str],
        actions_taken: list[ActionTaken],
        step: str,
        synthetic: bool,
        reason: str,
        flags: list[str],
    ) -> None:
        del flags, reason
        packet = self._packet(
            case_id,
            customer,
            tx,
            shown,
            band,
            fraud_score,
            prob,
            version,
            lang,
            facts,
            actions_taken,
            step,
            synthetic,
        )
        self._store_handoff(case_id, packet, "fraud_model")

    def _store_handoff(self, case_id: str, packet: HandoffPacket, reason: str) -> None:
        del reason
        now = datetime.now(UTC)
        self.ops.insert_handoff(
            {
                "handoff_id": new_case_id(),
                "case_id": case_id,
                "status": "waiting",
                "packet": packet.model_dump(mode="json"),
                "created_at": now,
                "updated_at": now,
            }
        )
        stored = self.ops.get_handoff(case_id)
        ok = stored is not None and stored["packet"]["case_id"] == case_id
        self._event(
            case_id,
            "tool",
            "handoff",
            {"packet_case_id": case_id},
            "verified" if ok else "failed",
        )

    def _packet(
        self,
        case_id: str,
        customer: Customer,
        tx: Transaction,
        shown: dict[str, str],
        band: str,
        fraud_score: float | None,
        prob: float | None,
        version: str,
        lang: str,
        facts: list[str],
        actions_taken: list[ActionTaken],
        step: str,
        synthetic: bool,
    ) -> HandoffPacket:
        safe_band = band if band in {"high", "review", "low", "out_of_scope"} else "review"
        language = lang if lang in {"es", "pt"} else "other"
        base = [
            f"merchant={tx.merchant_name}",
            f"status={tx.transaction_status}",
            f"fraud_score={fraud_score}",
            f"utc={shown['utc']}",
            f"customer_local={shown['label']}",
            f"tz={shown['tz']}",
        ]
        if synthetic:
            base.append("synthetic_duplicate=1")
        return HandoffPacket(
            case_id=case_id,
            customer_key=customer.customer_key,
            language=language,  # type: ignore[arg-type]
            transaction=TransactionFacts(
                transaction_key=tx.transaction_key,
                product_key=tx.product_key,
                merchant_name=tx.merchant_name,
                merchant_category=tx.merchant_category,
                transaction_city=tx.transaction_city,
                transaction_country=tx.transaction_country,
                transaction_status=tx.transaction_status,
                amount=tx.amount,
                currency=tx.currency,
                transaction_ts_utc=shown["utc"],
                customer_tz=shown["tz"],
                transaction_ts_customer_local=shown["label"],
                local_time_abbreviation=shown["abbreviation"],
            ),
            verified_facts=base + facts,
            triage=TriageInfo(
                band=safe_band,  # type: ignore[arg-type]
                fraud_score=fraud_score,
                model_risk_score=prob,
                model_version=version,
            ),
            actions_taken=actions_taken,
            open_questions=[],
            recommended_next_step=step,
            synthetic_duplicate=synthetic,
        )

    def _supersede(
        self,
        case: dict[str, Any],
        *,
        decision: str | None,
        closed: datetime | None,
        status: str,
        reason: str | None,
        packet_complete: bool | None,
        state_case_type: str | None = None,
        flags: list[str] | None = None,
        prob: float | None | object = ...,
        version: str | None = None,
    ) -> None:
        previous = self._current(str(case["case_id"]))
        audit_id = new_case_id()
        created = previous["case_created_at"] if previous else case["created_at"]
        inherited = ""
        if previous is not None:
            inherited = str(previous.get("case_type") or "")
        case_type = state_case_type or str(case.get("case_type") or inherited or "other")
        self._audit(
            case_id=str(case["case_id"]),
            audit_id=audit_id,
            supersedes=None if previous is None else str(previous["audit_id"]),
            case_type=case_type,
            customer=self._customer(str(case["customer_key"])),
            status=status,
            created=created,
            closed=closed,
            decision=decision,
            automation=bool(previous["automation_attempted"]) if previous else False,
            reason=reason,
            packet_complete=packet_complete,
            lang=str(case["language"]),
            version=version
            or (str(previous["rule_or_model_version"]) if previous else RULE_VERSION),
            fraud_score=None if previous is None else _float(previous.get("fraud_score")),
            prob=_resolved_prob(prob, previous),
            flags=flags
            if flags is not None
            else (list(previous["guardrail_flags"]) if previous else []),
            is_eval=bool(case.get("is_eval_case")),
            eval_run_id=case.get("eval_run_id"),
            case_source=case.get("case_source"),
        )
        now = datetime.now(UTC)
        self.ops.update_case(str(case["case_id"]), {"latest_audit_id": audit_id, "updated_at": now})

    def _audit(
        self,
        *,
        case_id: str,
        audit_id: str,
        supersedes: str | None,
        case_type: str,
        customer: Customer,
        status: str,
        created: object,
        closed: object,
        decision: str | None,
        automation: bool,
        reason: str | None,
        packet_complete: bool | None,
        lang: str,
        version: str,
        fraud_score: float | None,
        prob: float | None,
        flags: list[str],
        is_eval: bool,
        eval_run_id: str | None,
        case_source: str | None,
    ) -> None:
        self.ops.append_audit_case(
            {
                "audit_id": audit_id,
                "case_id": case_id,
                "supersedes_audit_id": supersedes,
                "recorded_at": datetime.now(UTC),
                "case_type": case_type,
                "customer_segment": customer.customer_segment,
                "final_resolution_status": status,
                "case_created_at": created,
                "case_closed_at": closed,
                "decision": decision,
                "automation_attempted": automation,
                "handoff_reason": reason,
                "handoff_packet_complete": packet_complete,
                "language": lang,
                "country": country_code(customer.customer_country),
                "accent_group": None,
                "rule_or_model_version": version,
                "prompt_version": self.settings.prompt_version,
                "fraud_score": fraud_score,
                "model_risk_score": prob,
                "guardrail_flags": flags,
                "is_eval_case": is_eval,
                "eval_run_id": eval_run_id,
                "case_source": case_source,
            }
        )

    def _injection(
        self,
        customer_key: str,
        lang: str,
        flags: list[str],
        eval_run_id: str | None,
        case_source: str | None,
    ) -> CaseResult:
        flags.append("injection_detected")
        customer = self.bank.get_customer(customer_key)
        if customer is None:
            raise APIError(404, "not_found", "Customer not found")
        case_id = new_case_id()
        now = datetime.now(UTC)
        is_eval = bool(eval_run_id or case_source)
        audit_id = new_case_id()
        self.ops.insert_case(
            {
                "case_id": case_id,
                "customer_key": customer_key,
                "transaction_key": None,
                "state": "closed",
                "language": lang,
                "case_type": "other",
                "created_at": now,
                "updated_at": now,
                "closed_at": now,
                "latest_audit_id": audit_id,
                "is_eval_case": is_eval,
                "eval_run_id": eval_run_id,
                "case_source": case_source,
            }
        )
        self._audit(
            case_id=case_id,
            audit_id=audit_id,
            supersedes=None,
            case_type="other",
            customer=customer,
            status="injection_blocked",
            created=now,
            closed=now,
            decision="abandoned",
            automation=False,
            reason="injection_detected",
            packet_complete=None,
            lang=lang,
            version=RULE_VERSION,
            fraud_score=None,
            prob=None,
            flags=flags,
            is_eval=is_eval,
            eval_run_id=eval_run_id,
            case_source=case_source,
        )
        return CaseResult(
            case_id,
            reply_injection(lang),
            lang,
            "other",
            "out_of_scope",
            [],
            None,
            "closed",
            eval_run_id,
            case_source,
            flags,
        )

    def _clarify(
        self,
        customer_key: str,
        lang: str,
        flags: list[str],
        eval_run_id: str | None,
        case_source: str | None,
    ) -> CaseResult:
        customer = self.bank.get_customer(customer_key)
        if customer is None:
            raise APIError(404, "not_found", "Customer not found")
        case_id = new_case_id()
        now = datetime.now(UTC)
        is_eval = bool(eval_run_id or case_source)
        audit_id = new_case_id()
        self.ops.insert_case(
            {
                "case_id": case_id,
                "customer_key": customer_key,
                "transaction_key": None,
                "state": "clarifying",
                "language": lang,
                "case_type": "other",
                "created_at": now,
                "updated_at": now,
                "closed_at": now,
                "latest_audit_id": audit_id,
                "is_eval_case": is_eval,
                "eval_run_id": eval_run_id,
                "case_source": case_source,
            }
        )
        self._audit(
            case_id=case_id,
            audit_id=audit_id,
            supersedes=None,
            case_type="other",
            customer=customer,
            status="clarifying",
            created=now,
            closed=now,
            decision="abandoned",
            automation=False,
            reason=None,
            packet_complete=None,
            lang=lang,
            version=RULE_VERSION,
            fraud_score=None,
            prob=None,
            flags=flags,
            is_eval=is_eval,
            eval_run_id=eval_run_id,
            case_source=case_source,
        )
        return CaseResult(
            case_id,
            reply_clarify(lang),
            lang,
            "other",
            "out_of_scope",
            [],
            None,
            "clarifying",
            eval_run_id,
            case_source,
            flags,
        )

    def _result(
        self,
        case_id: str,
        reply: str,
        case_type: str,
        band: str,
        actions: list[ActionButton],
        prob: float | None,
    ) -> CaseResult:
        case = self.ops.get_case(case_id)
        assert case is not None
        return CaseResult(
            case_id,
            reply,
            str(case["language"]),
            case_type,
            band,
            actions,
            prob,
            str(case["state"]),
            case.get("eval_run_id"),
            case.get("case_source"),
        )

    def _own_case(self, customer_key: str, case_id: str) -> dict[str, Any]:
        case = self.ops.get_case(case_id)
        if case is None or case["customer_key"] != customer_key:
            raise APIError(404, "not_found", "Case not found")
        return case

    def _tx(self, case: dict[str, Any]) -> Transaction:
        tx = self.bank.get_transaction(str(case["customer_key"]), str(case["transaction_key"]))
        if tx is None:
            raise APIError(404, "not_found", "Charge not found")
        return tx

    def _customer(self, customer_key: str) -> Customer:
        customer = self.bank.get_customer(customer_key)
        if customer is None:
            raise APIError(404, "not_found", "Customer not found")
        return customer

    def _event(
        self,
        case_id: str,
        kind: str,
        name: str,
        detail: dict[str, Any],
        verification: str,
    ) -> None:
        self.ops.append_event(
            {
                "audit_id": new_id("evt"),
                "case_id": case_id,
                "trace_id": case_id,
                "kind": kind,
                "name": name,
                "detail": detail,
                "verification_status": verification,
                "recorded_at": datetime.now(UTC),
            }
        )

    def _current(self, case_id: str) -> dict[str, Any] | None:
        rows = [row for row in self.ops.current_audit_cases() if row["case_id"] == case_id]
        return rows[0] if rows else None

    def _flags(self, case: dict[str, Any] | str) -> list[str]:
        case_id = case if isinstance(case, str) else str(case["case_id"])
        current = self._current(case_id)
        if current is None:
            return []
        return list(current["guardrail_flags"])

    def _rewrite_flags(self, case: dict[str, Any], flags: list[str]) -> None:
        current = self._current(str(case["case_id"]))
        if current is None:
            return
        self._supersede(
            case,
            decision=current.get("decision"),
            closed=current.get("case_closed_at"),
            status=str(current.get("final_resolution_status") or ""),
            reason=current.get("handoff_reason"),
            packet_complete=current.get("handoff_packet_complete"),
            flags=flags,
        )

    def _version(self, case: dict[str, Any]) -> str:
        current = self._current(str(case["case_id"]))
        if current is None:
            return RULE_VERSION
        return str(current.get("rule_or_model_version") or RULE_VERSION)

    def _prob(self, case: dict[str, Any]) -> float | None:
        current = self._current(str(case["case_id"]))
        if current is None:
            return None
        return _float(current.get("model_risk_score"))


def _resolved_prob(prob: object, previous: dict[str, Any] | None) -> float | None:
    if prob is ...:
        if previous is None:
            return None
        return _float(previous.get("model_risk_score"))
    return _float(prob)


def _redact(text: str) -> tuple[str, bool]:
    cleaned = redact(text)
    return cleaned, cleaned != text


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
