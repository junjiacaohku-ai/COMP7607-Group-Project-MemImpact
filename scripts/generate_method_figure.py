from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "docs" / "assets"
COLORS = {
    "ink": "#172033",
    "muted": "#64748B",
    "line": "#D9E2EC",
    "background": "#F7F9FC",
    "blue": "#2563EB",
    "violet": "#7C3AED",
    "orange": "#D97706",
    "green": "#059669",
}


def rounded_box(ax, x, y, width, height, facecolor, edgecolor, radius=0.16, lw=1.2):
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        linewidth=lw,
        edgecolor=edgecolor,
        facecolor=facecolor,
        zorder=2,
    )
    ax.add_patch(box)
    return box


def chip(ax, x, y, width, text, color):
    rounded_box(ax, x, y, width, 0.46, f"{color}10", f"{color}35", radius=0.12, lw=0.9)
    ax.text(
        x + width / 2,
        y + 0.23,
        text,
        ha="center",
        va="center",
        fontsize=10.5,
        color=color,
        fontweight="bold",
        zorder=3,
    )


def bullet(ax, x, y, text, color, fontsize=12.0):
    ax.add_patch(Circle((x, y), 0.045, facecolor=color, edgecolor="none", zorder=3))
    ax.text(x + 0.18, y, text, ha="left", va="center", fontsize=fontsize, color=COLORS["ink"], zorder=3)


def main():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "svg.fonttype": "none",
        }
    )
    fig, ax = plt.subplots(figsize=(18, 8.4), dpi=100)
    fig.patch.set_facecolor(COLORS["background"])
    ax.set_facecolor(COLORS["background"])
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 8.4)
    ax.axis("off")

    ax.text(0.65, 7.82, "MEMIMPACT  /  METHOD", fontsize=11.5, color=COLORS["blue"], fontweight="bold")
    ax.text(
        0.65,
        7.22,
        "Counterfactual memory auditing, from rollout to evidence",
        fontsize=25,
        color=COLORS["ink"],
        fontweight="bold",
    )
    ax.text(
        0.65,
        6.73,
        "Measure how each memory changes a proposed action before deciding what to verify.",
        fontsize=13.5,
        color=COLORS["muted"],
    )
    stages = [
        {
            "x": 0.65,
            "color": COLORS["blue"],
            "step": "01  PLAN",
            "title": "Full-memory planning",
            "badge": "S = 3",
            "bullets": ["Task + 3 memories", "Full-memory samples", "Canonical action"],
        },
        {
            "x": 5.05,
            "color": COLORS["violet"],
            "step": "02  INTERVENE",
            "title": "Memory ablation",
            "badge": "k = 3",
            "bullets": ["Remove each memory", "Plan-only rollouts", "Ablated actions"],
        },
        {
            "x": 9.45,
            "color": COLORS["orange"],
            "step": "03  SCORE & VERIFY",
            "title": "Score & verification",
            "badge": "B = 1 / 3",
            "bullets": ["Subtract planner noise", "Rank impact + age", "Verify within budget"],
        },
        {
            "x": 13.85,
            "color": COLORS["green"],
            "step": "04  ACT & EVALUATE",
            "title": "Approved action",
            "badge": "ISOLATED",
            "bullets": ["Replan on refutation", "Execute approved action", "Success, harm, cost"],
        },
    ]
    card_y, card_w, card_h = 1.65, 3.5, 4.45
    for index, stage in enumerate(stages):
        x, color = stage["x"], stage["color"]
        rounded_box(ax, x + 0.05, card_y - 0.07, card_w, card_h, "#E9EEF5", "#E9EEF5", radius=0.22, lw=0)
        rounded_box(ax, x, card_y, card_w, card_h, "#FFFFFF", COLORS["line"], radius=0.22, lw=1.1)
        rounded_box(ax, x, card_y + card_h - 0.14, card_w, 0.14, color, color, radius=0.06, lw=0)
        ax.text(x + 0.3, 5.64, stage["step"], fontsize=10.5, color=color, fontweight="bold", va="center")
        ax.text(x + 0.3, 5.08, stage["title"], fontsize=14.2, color=COLORS["ink"], fontweight="bold", va="center")
        if index == 2:
            ax.text(x + 0.3, 4.36, r"$\widetilde{F}_i=\max(0,\widehat{F}_i-\widehat{F}_0)$", fontsize=17, color=color)
            bullet_y = [3.65, 2.95, 2.25]
        else:
            bullet_y = [4.18, 3.43, 2.68]
        for y, text in zip(bullet_y, stage["bullets"]):
            bullet(ax, x + 0.34, y, text, color)
        if index < len(stages) - 1:
            next_x = stages[index + 1]["x"]
            arrow = FancyArrowPatch(
                (x + card_w + 0.13, 3.86),
                (next_x - 0.13, 3.86),
                arrowstyle="-|>",
                mutation_scale=18,
                linewidth=1.8,
                color="#94A3B8",
                zorder=4,
            )
            ax.add_patch(arrow)

    rounded_box(ax, 0.65, 0.43, 16.7, 0.68, "#EEF3F9", "#EEF3F9", radius=0.18, lw=0)
    notes = [
        (1.0, COLORS["blue"], "PLANNING-ONLY AUDIT"),
        (6.35, COLORS["orange"], "EVIDENCE-GATED EXECUTION"),
        (12.1, COLORS["green"], "COMPLETE TRACES"),
    ]
    for x, color, text in notes:
        ax.add_patch(Circle((x, 0.77), 0.06, facecolor=color, edgecolor="none"))
        ax.text(x + 0.18, 0.77, text, fontsize=10.5, color=COLORS["muted"], fontweight="bold", va="center")

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_DIRECTORY / "memimpact-method.png", dpi=160, bbox_inches="tight", pad_inches=0.12, facecolor=fig.get_facecolor())
    svg_path = OUTPUT_DIRECTORY / "memimpact-method.svg"
    fig.savefig(svg_path, bbox_inches="tight", pad_inches=0.12, facecolor=fig.get_facecolor())
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
        encoding="utf-8",
    )
    plt.close(fig)
    print(f"Saved method figure to {OUTPUT_DIRECTORY}")


if __name__ == "__main__":
    main()
