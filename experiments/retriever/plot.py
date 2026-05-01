"""
plot_analysis.py
----------------
Ablation plots across configurations.
Run with: python -m src.plot_analysis
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from itertools import cycle

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CSV_PATH  = "data/results/global/general_metrics.csv"
PLOTS_DIR = "data/results/plots"

PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974",
]

LINESTYLES = ["-", "--", "-.", ":"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def load_csv():
    df = pd.read_csv(CSV_PATH)

    df["k"]         = df["k"].astype(int)
    df["clean"]     = df["clean"].astype(str).str.lower().map({"true": True, "false": False})
    df["rerank"]    = df["rerank"].astype(str).str.lower()
    df["k_rerank"]  = pd.to_numeric(df["k_rerank"], errors="coerce")
    df["chunk_max"] = pd.to_numeric(df["chunk_max"], errors="coerce")

    return df[df["k"].between(1, 10)]


def color_linestyle_map(labels):
    colors = cycle(PALETTE)
    styles = cycle(LINESTYLES)
    return {label: (next(colors), next(styles)) for label in labels}


# ---------------------------------------------------------------------------
# Plot core
# ---------------------------------------------------------------------------

def plot_metric_vs_k(ax, groups, metric, cl_map, title):
    for label, sub in groups.items():

        sub_k = (
            sub.groupby("k", as_index=False)[metric]
            .mean()
            .sort_values("k")
        )

        color, ls = cl_map[label]

        ax.plot(
            sub_k["k"],
            sub_k[metric],
            label=label,
            color=color,
            linestyle=ls,
            marker="o",
            markersize=4,
            linewidth=2 if ls == "--" else 1.6
        )

    ax.set_title(title, fontsize=11)
    ax.set_xlabel("k")
    ax.set_ylabel(metric.upper())
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, loc="best")


def plot_mrr_bar(ax, groups, cl_map, title):
    labels = list(groups.keys())
    values = [groups[l]["mrr"].iloc[0] for l in labels]
    colors = [cl_map[l][0] for l in labels]

    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.7)
    ax.bar_label(bars, fmt="%.3f", fontsize=8, padding=2)

    ax.set_title(title, fontsize=11)
    ax.set_ylabel("MRR")
    ax.set_ylim(0, min(1.05, max(values) * 1.15))
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)


def plot_latency_bxp(ax, groups, cl_map, title):
    bxp_stats = []
    colors = []

    for label, sub in groups.items():
        row = sub.iloc[0]

        bxp_stats.append({
            "med":    row["latency_q2_ms"],
            "q1":     row["latency_q1_ms"],
            "q3":     row["latency_q3_ms"],
            "whislo": row["latency_min_ms"],
            "whishi": row["latency_max_ms"],
            "mean":   row["latency_mean_ms"],
            "label":  label,
            "fliers": [],
        })

        colors.append(cl_map[label][0])

    bp = ax.bxp(bxp_stats, showmeans=True, meanline=True,
                patch_artist=True, widths=0.5)

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_title(title, fontsize=11)
    ax.set_ylabel("Latency (ms)")
    ax.set_xticklabels([s["label"] for s in bxp_stats],
                       rotation=25, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)


def save_metric_plots(stage_dir, groups, cl_map, title, include_latency=False):
    ensure_dir(stage_dir)

    for metric in ["precision", "recall", "ndcg"]:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        plot_metric_vs_k(ax, groups, metric, cl_map, f"{title} — {metric.upper()}@k")
        fig.tight_layout()
        fig.savefig(os.path.join(stage_dir, f"{metric}.png"), dpi=150)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(max(5, len(groups) * 0.9), 4.5))
    plot_mrr_bar(ax, groups, cl_map, f"{title} — MRR")
    fig.tight_layout()
    fig.savefig(os.path.join(stage_dir, "mrr.png"), dpi=150)
    plt.close(fig)

    if include_latency:
        fig, ax = plt.subplots(figsize=(max(5, len(groups) * 0.9), 4.5))
        plot_latency_bxp(ax, groups, cl_map, f"{title} — Latency")
        fig.tight_layout()
        fig.savefig(os.path.join(stage_dir, "latency.png"), dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------

def stage1(df):
    sub = df[
        (df["level"] == "l2") &
        (df["embed_model"] == "bge") &
        (df["chunk_max"] == 1024) &
        (df["rerank"] == "no") &
        (df["mode"] == "dense") &
        (df["aggregation"] == "mean")
    ]

    groups = {
        "clean=True":  sub[sub["clean"]],
        "clean=False": sub[~sub["clean"]],
    }

    cl_map = color_linestyle_map(groups.keys())
    save_metric_plots(os.path.join(PLOTS_DIR, "clean"),
                      groups, cl_map, "Data Cleaning")


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------

def stage2(df):
    sub = df[
        (df["level"] == "l2") &
        (df["clean"]) &
        (df["embed_model"] == "bge") &
        (df["chunk_max"] == 1024) &
        (df["rerank"] == "no")
    ]

    groups = {
        f"{m}_{a}": g
        for (m, a), g in sub.groupby(["mode", "aggregation"])
    }

    cl_map = color_linestyle_map(groups.keys())
    save_metric_plots(os.path.join(PLOTS_DIR, "retrieval"),
                      groups, cl_map, "Retrieval Variants", True)


# ---------------------------------------------------------------------------
# Stage 3 (FULL FIXED LOGIC)
# ---------------------------------------------------------------------------

def stage3(df):
    valid = [("dense","mean"), ("dense","max"), ("hybrid","mean"), ("hybrid","max")]

    sub = df[
        (df["level"] == "l2") &
        (df["clean"]) &
        (df["embed_model"] == "bge") &
        (df["chunk_max"] == 1024) &
        (df[["mode","aggregation"]].apply(tuple, axis=1).isin(valid)) &
        (
            (df["rerank"] == "no") |
            ((df["rerank"] == "yes") & (df["k_rerank"] == 20))
        )
    ].copy()

    # ✅ explicit structured columns (NO STRING LOGIC)
    sub["variant"] = sub["mode"] + "_" + sub["aggregation"]
    sub["rerank_flag"] = sub["rerank"]  # SOURCE OF TRUTH

    groups = {}
    for (variant, rr), g in sub.groupby(["variant", "rerank_flag"]):
        label = f"{variant} ({'rerank@20' if rr=='yes' else 'no rerank'})"
        groups[label] = g

    # stable colors per variant
    variants = sorted(sub["variant"].unique())
    palette_cycle = cycle(PALETTE)
    variant_colors = {v: next(palette_cycle) for v in variants}

    cl_map = {}
    for label in groups:
        variant = label.split(" (")[0]
        rr = "rerank" if "rerank" in label and "no rerank" not in label else "no"

        cl_map[label] = (
            variant_colors[variant],
            "--" if "rerank" in label and "no rerank" not in label else "-"
        )

    save_metric_plots(os.path.join(PLOTS_DIR, "rerank"),
                      groups, cl_map, "Rerank Effect", True)


# ---------------------------------------------------------------------------
# Stage 4
# ---------------------------------------------------------------------------

def stage4(df):
    sub = df[
        (df["level"] == "l2") &
        (df["clean"]) &
        (df["embed_model"] == "bge") &
        (df["mode"] == "dense") &
        (df["aggregation"] == "mean") &
        (df["rerank"] == "yes") &
        (df["k_rerank"] == 20)
    ]

    groups = {f"chunk={int(c)}": g for c, g in sub.groupby("chunk_max")}

    cl_map = color_linestyle_map(groups.keys())
    save_metric_plots(os.path.join(PLOTS_DIR, "chunk"),
                      groups, cl_map, "Chunk Size", True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = load_csv()

    ensure_dir(PLOTS_DIR)

    stage1(df)
    stage2(df)
    stage3(df)
    stage4(df)

    print(f"\nAll plots saved to {PLOTS_DIR}/")