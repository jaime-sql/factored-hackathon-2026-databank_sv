"""Chart 05: where "no reconozco este cargo" disputes would go (Spanish, deck style).

Built only from the locked artifact ``static/data/sim_curve.json`` (validation split,
default cut). No database, no re-scoring, test split never read.

A) Every validation charge, routed by the live rules: rule path, HIGH, REVIEW, LOW.
B) Extreme bound: every dispute is real fraud. Same routing over the 610 validation frauds.
   LOW here is fraud the AI would close without a human (the locked 29/610).

Colours and type follow the deck style guide (static/css/app.css tokens).
Run: python analytics/chart_05_dispute_mix.py  -> analytics/charts/05_dispute_case_mix.png
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(os.path.dirname(HERE), "static", "data", "sim_curve.json")
OUT = os.path.join(HERE, "charts", "05_dispute_case_mix.png")
SOURCE_SHA = os.environ.get("SIM_CURVE_SHA", "598c341")

PAPER, CARD, INK, MUTED, MUTED2, LINE = (
    "#f6f1e7",
    "#fffdf8",
    "#1c1915",
    "#3f3a34",
    "#4d463e",
    "#e2d8c8",
)
SEGMENTS = [
    ("rule", "Regla (sin humano)", MUTED2),
    ("high", "ALTO (bloqueo + humano)", "#8a3d12"),
    ("review", "REVISIÓN (humano)", "#7a5200"),
    ("low", "BAJO (la IA resuelve)", "#0f6e56"),
]
SERIF = ["Iowan Old Style", "Palatino Linotype", "Palatino", "Georgia", "DejaVu Serif"]
SANS = ["Segoe UI", "Helvetica", "Arial", "Noto Sans", "DejaVu Sans"]


def load_counts(path=SIM):
    """Return (charges, frauds, summary) count dicts from sim_curve.json."""
    with open(path, encoding="utf-8") as handle:
        sim = json.load(handle)
    s = next(pt for pt in sim["points"] if pt.get("default"))
    missed = sim["default_point_summary"]["missed_fraud"]
    assert missed == s["missed_fraud"], "default point and summary disagree"
    n_fraud = int(sim["n_fraud_total"])
    charges = {
        "rule": int(sim["n_rule"]),
        "high": int(sim["n_high"]),
        "review": int(s["n_review"]),
        "low": int(s["n_low"]),
    }
    frauds = {
        "rule": int(sim["fraud_in_rule"]),
        "high": int(sim["fraud_in_high"]),
        "low": int(missed["k"]),
    }
    frauds["review"] = n_fraud - frauds["rule"] - frauds["high"] - frauds["low"]
    assert sum(charges.values()) == int(sim["n_charges"]), "charge counts do not add up"
    assert int(missed["n"]) == n_fraud, "missed-fraud n differs from n_fraud_total"
    assert frauds["review"] >= 0
    return charges, frauds, sim


def fmt_pct(k, n):
    p = 100.0 * k / n
    return f"{p:.2f}%" if p < 1 else f"{p:.1f}%"


def main():
    charges, frauds, sim = load_counts()
    n_ch, n_fr = int(sim["n_charges"]), int(sim["n_fraud_total"])
    missed = sim["default_point_summary"]["missed_fraud"]
    wrongful = (frauds["low"] + frauds["rule"]) / n_ch * 10000

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = SANS
    plt.rcParams["font.serif"] = SERIF

    fig, ax = plt.subplots(figsize=(12, 5.2), dpi=160)
    fig.patch.set_facecolor(CARD)
    ax.set_facecolor(CARD)

    rows = [
        (1, f"A  Todos los cargos\n(n = {n_ch:,})", charges, n_ch),
        (0, f"B  Solo fraude, cota extrema\n(n = {n_fr:,})", frauds, n_fr),
    ]
    for y, _, counts, n in rows:
        left = 0.0
        for key, label, colour in SEGMENTS:
            k = counts[key]
            w = 100.0 * k / n
            ax.barh(
                y,
                w,
                left=left,
                color=colour,
                height=0.52,
                edgecolor=CARD,
                linewidth=1.5,
                label=label if y == 1 else None,
            )
            if w >= 9:
                ax.text(
                    left + w / 2,
                    y + 0.07,
                    fmt_pct(k, n),
                    ha="center",
                    va="center",
                    fontsize=12,
                    color="#ffffff",
                    fontweight="bold",
                    family="serif",
                )
                ax.text(
                    left + w / 2,
                    y - 0.13,
                    f"{k:,} / {n:,}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="#ffffff",
                )
            left += w

    arrow = dict(arrowstyle="-", color=MUTED, lw=0.8)
    ax.annotate(
        f"Regla {charges['rule']:,} / {n_ch:,} ({fmt_pct(charges['rule'], n_ch)})   ·   "
        f"ALTO {charges['high']:,} / {n_ch:,} ({fmt_pct(charges['high'], n_ch)})",
        xy=(1.5, 1.27),
        xytext=(0.5, 1.47),
        fontsize=9.5,
        color=MUTED,
        arrowprops=arrow,
        va="center",
    )
    ax.annotate(
        f"Regla {frauds['rule']} / {n_fr} ({fmt_pct(frauds['rule'], n_fr)})",
        xy=(100.0 * frauds["rule"] / n_fr / 2, -0.27),
        xytext=(0.5, -0.55),
        fontsize=9.5,
        color=MUTED,
        arrowprops=arrow,
        va="center",
    )
    low_pct = 100.0 * missed["k"] / missed["n"]
    ax.annotate(
        f"BAJO = fraude que la IA cerraría sin humano: {missed['k']} / {missed['n']} = "
        f"{low_pct:.2f}%  (IC 95% {100 * missed['ci_low']:.2f}–{100 * missed['ci_high']:.2f}%)",
        xy=(100 - low_pct / 2, -0.27),
        xytext=(36, -0.55),
        fontsize=9.5,
        color=INK,
        arrowprops=arrow,
        va="center",
    )

    ax.set_yticks([r[0] for r in rows])
    ax.set_yticklabels([r[1] for r in rows], fontsize=11, color=INK)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.8, 1.7)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xticklabels([f"{x}%" for x in range(0, 101, 20)], fontsize=9, color=MUTED)
    ax.xaxis.grid(True, color=LINE, lw=0.8)
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors=MUTED)

    fig.suptitle(
        "Adónde irían las disputas «no reconozco este cargo»",
        x=0.02,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color=INK,
        family="serif",
        y=0.99,
    )
    ax.set_title(
        "A: todos los cargos de validación, con el corte por defecto "
        f"({100 * sim['default_point_summary']['automation_rate']:.2f}% se resuelve sin humano).\n"
        "B: cota extrema, no una estimación: supone que toda disputa es fraude real. "
        "Las quejas no se pueden vincular a transacciones.",
        loc="left",
        fontsize=9.5,
        color=MUTED,
        pad=30,
    )
    ax.legend(
        ncol=4,
        loc="upper left",
        bbox_to_anchor=(0, 1.15),
        frameon=False,
        fontsize=10,
        labelcolor=INK,
    )
    fig.text(
        0.02,
        0.035,
        f"Fraudes cerrados sin revisión humana (BAJO + regla): ({frauds['low']} + "
        f"{frauds['rule']}) / {n_ch:,} = {wrongful:.2f} por 10k cargos.",
        fontsize=8.5,
        color=MUTED,
    )
    fig.text(
        0.02,
        0.005,
        f"Fuente: static/data/sim_curve.json @ {SOURCE_SHA} · validación "
        f"(corte {sim['t_low_default']:.7f})",
        fontsize=8.5,
        color=MUTED,
    )
    plt.tight_layout(rect=(0, 0.06, 1, 1))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor=CARD)
    print(OUT)


if __name__ == "__main__":
    main()
