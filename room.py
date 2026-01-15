import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt


def safe_title(s: str) -> str:
    # Keep chart titles readable and safe
    return str(s).strip().replace("\n", " ")


def rotation_quality_label(rate: float) -> str:
    if rate < 0.2:
        return "Very low (poor rotation)"
    if rate < 0.4:
        return "Low (needs improvement)"
    if rate < 0.6:
        return "Moderate"
    return "High (good rotation)"


def coerce_datetime(series: pd.Series) -> pd.Series:
    """
    Tries common date parsing patterns robustly.
    If your CSV has messy dates, this will still usually behave.
    """
    dt = pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    return dt


def ensure_output_dir(base: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    out = base / f"report_{ts}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_df(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False)


def plot_and_save(fig, out_path: Path):
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Generate housekeeping management visuals + summaries from CSV.")
    parser.add_argument("--csv", required=True, help="Path to input CSV")
    parser.add_argument("--out", default=".", help="Output directory base (default: current folder)")
    parser.add_argument("--top", type=int, default=10, help="Top N for housekeepers/user charts (default: 10)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_base = Path(args.out)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    out_dir = ensure_output_dir(out_base)

    # ---- Load ----
    df = pd.read_csv(csv_path)

    required_cols = [
        "Room Number",
        "Room Type",
        "FD Status",
        "HSK Status Before",
        "HSK Status After",
        "Housekeeper Before",
        "Housekeeper After",
        "Username",
        "Date",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in CSV: {missing}")

    # Normalize types
    df["Room Number"] = df["Room Number"].astype(str).str.strip()
    df["Room Type"] = df["Room Type"].astype(str).str.strip()
    df["FD Status"] = df["FD Status"].astype(str).str.strip()
    df["HSK Status Before"] = df["HSK Status Before"].astype(str).str.strip()
    df["HSK Status After"] = df["HSK Status After"].astype(str).str.strip()
    df["Housekeeper Before"] = df["Housekeeper Before"].fillna("Unknown").astype(str).str.strip()
    df["Housekeeper After"] = df["Housekeeper After"].fillna("Unknown").astype(str).str.strip()
    df["Username"] = df["Username"].fillna("Unknown").astype(str).str.strip()

    df["DateTime"] = coerce_datetime(df["Date"])
    # If Date parsing fails, we'll still report but day-based charts may be limited.
    df["Day"] = df["DateTime"].dt.date

    # Work happened flag
    df["HSK_Changed"] = df["HSK Status Before"] != df["HSK Status After"]

    # Transition label
    df["HSK_Transition"] = df["HSK Status Before"].fillna("") + " → " + df["HSK Status After"].fillna("")

    # ---- Summaries ----
    total_rows = len(df)
    total_rooms_unique = df["Room Number"].nunique()
    changed_count = int(df["HSK_Changed"].sum())
    change_rate = (changed_count / total_rows) if total_rows else 0.0

    # Overall summary table
    overall = pd.DataFrame([{
        "Total rows": total_rows,
        "Unique rooms": total_rooms_unique,
        "HSK status changes (count)": changed_count,
        "HSK status changes (rate)": round(change_rate, 4),
        "Date parse success rate": round(df["DateTime"].notna().mean(), 4),
        "Generated at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Source CSV": str(csv_path.resolve()),
    }])
    save_df(overall, out_dir / "summary_overall.csv")

    # By day (if dates parse)
    if df["Day"].notna().any():
        by_day = (
            df.groupby("Day", dropna=True)
              .agg(
                  rows=("Room Number", "size"),
                  unique_rooms=("Room Number", "nunique"),
                  changed=("HSK_Changed", "sum"),
              )
              .reset_index()
        )
        by_day["change_rate"] = (by_day["changed"] / by_day["rows"]).round(4)
        save_df(by_day, out_dir / "summary_by_day.csv")
    else:
        by_day = None

    # By room type
    by_room_type = (
        df.groupby("Room Type", dropna=False)
          .agg(
              rows=("Room Number", "size"),
              unique_rooms=("Room Number", "nunique"),
              changed=("HSK_Changed", "sum"),
          )
          .reset_index()
          .sort_values(["changed", "rows"], ascending=[False, False])
    )
    by_room_type["change_rate"] = (by_room_type["changed"] / by_room_type["rows"]).round(4)
    save_df(by_room_type, out_dir / "summary_by_room_type.csv")

    # By Housekeeper After (who closed/ended state)
    by_hk_after = (
        df.groupby("Housekeeper After", dropna=False)
          .agg(
              rows=("Room Number", "size"),
              changed=("HSK_Changed", "sum"),
              unique_rooms=("Room Number", "nunique"),
          )
          .reset_index()
          .sort_values(["changed", "rows"], ascending=[False, False])
    )
    by_hk_after["change_rate"] = (by_hk_after["changed"] / by_hk_after["rows"]).round(4)
    save_df(by_hk_after, out_dir / "summary_by_housekeeper_after.csv")

    # By Username
    by_user = (
        df.groupby("Username", dropna=False)
          .agg(
              rows=("Room Number", "size"),
              changed=("HSK_Changed", "sum"),
              unique_rooms=("Room Number", "nunique"),
          )
          .reset_index()
          .sort_values(["rows", "changed"], ascending=[False, False])
    )
    by_user["change_rate"] = (by_user["changed"] / by_user["rows"]).round(4)
    save_df(by_user, out_dir / "summary_by_username.csv")

    # Room uniqueness by user (rotation quality)
    uniqueness_by_user = (
        df.groupby("Username", dropna=False)
          .agg(
              total_actions=("Room Number", "size"),
              unique_rooms=("Room Number", "nunique"),
              status_changes=("HSK_Changed", "sum"),
          )
          .reset_index()
    )
    uniqueness_by_user["room_uniqueness_rate"] = (
        uniqueness_by_user["unique_rooms"] / uniqueness_by_user["total_actions"].replace(0, pd.NA)
    ).fillna(0.0)
    uniqueness_by_user["rotation_quality"] = uniqueness_by_user["room_uniqueness_rate"].map(rotation_quality_label)
    uniqueness_by_user = uniqueness_by_user.sort_values(
        ["room_uniqueness_rate", "total_actions"],
        ascending=[True, False],
    )
    uniqueness_by_user["room_uniqueness_rate"] = uniqueness_by_user["room_uniqueness_rate"].round(3)
    save_df(uniqueness_by_user, out_dir / "username_room_rotation_uniqueness.csv")

    # Transition matrix (Before -> After)
    transition = (
        df.pivot_table(
            index="HSK Status Before",
            columns="HSK Status After",
            values="Room Number",
            aggfunc="count",
            fill_value=0,
        )
        .sort_index()
    )

    # ---- Charts ----

    # 1) Daily volume
    if by_day is not None and len(by_day) > 0:
        fig = plt.figure()
        plt.plot(by_day["Day"], by_day["rows"], marker="o")
        plt.title("Daily volume (rows logged)")
        plt.xlabel("Day")
        plt.ylabel("Rows")
        plt.xticks(rotation=45, ha="right")
        plot_and_save(fig, out_dir / "daily_volume.png")

        # 2) Daily changes
        fig = plt.figure()
        plt.plot(by_day["Day"], by_day["changed"], marker="o")
        plt.title("Daily HSK status changes (Before ≠ After)")
        plt.xlabel("Day")
        plt.ylabel("Changed rows")
        plt.xticks(rotation=45, ha="right")
        plot_and_save(fig, out_dir / "daily_changes.png")

        # 3) HSK After distribution by day (stacked bar)
        # Keep top statuses for readability
        top_statuses = (
            df["HSK Status After"].value_counts()
              .head(8)
              .index
        )
        df_status = df[df["HSK Status After"].isin(top_statuses)].copy()
        status_by_day = (
            df_status.groupby(["Day", "HSK Status After"])
                     .size()
                     .unstack(fill_value=0)
                     .sort_index()
        )
        fig = plt.figure()
        status_by_day.plot(kind="bar", stacked=True, ax=plt.gca())
        plt.title("HSK Status After by day (top statuses)")
        plt.xlabel("Day")
        plt.ylabel("Count")
        plt.xticks(rotation=45, ha="right")
        plt.legend(title="HSK After", bbox_to_anchor=(1.02, 1), loc="upper left")
        plot_and_save(fig, out_dir / "hsk_after_by_day.png")

    # 4) Top housekeepers (After)
    top_n = max(1, int(args.top))
    hk_top = by_hk_after.head(top_n)
    fig = plt.figure()
    plt.barh(hk_top["Housekeeper After"].map(safe_title), hk_top["changed"])
    plt.title(f"Top {top_n} Housekeepers (by HSK changes, After)")
    plt.xlabel("Changed rows")
    plt.ylabel("Housekeeper After")
    plt.gca().invert_yaxis()
    plot_and_save(fig, out_dir / "top_housekeepers_after.png")

    # 5) Transition heatmap (Before -> After) using imshow (no seaborn)
    fig = plt.figure()
    mat = transition.values
    plt.imshow(mat, aspect="auto")
    plt.title("HSK Status Transition Matrix (Before → After)")
    plt.xlabel("HSK Status After")
    plt.ylabel("HSK Status Before")
    plt.xticks(range(len(transition.columns)), [safe_title(c) for c in transition.columns], rotation=45, ha="right")
    plt.yticks(range(len(transition.index)), [safe_title(i) for i in transition.index])

    # Annotate cells lightly (skip if huge)
    if mat.size <= 400:  # 20x20 cap for sanity
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                val = mat[i, j]
                if val != 0:
                    plt.text(j, i, str(val), ha="center", va="center")

    plot_and_save(fig, out_dir / "hsk_transition_heatmap.png")

    # ---- Final message ----
    print(f"\n✅ Done. Report generated at:\n{out_dir.resolve()}\n")
    print("Files created:")
    for p in sorted(out_dir.iterdir()):
        print(f" - {p.name}")


if __name__ == "__main__":
    main()