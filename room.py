import argparse
import html as htmllib
import shutil
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

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


def df_to_html_table(df: pd.DataFrame | None, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return '<div class="muted">No data available.</div>'
    display_df = df.head(max_rows).copy()
    return display_df.to_html(
        index=False,
        classes="table",
        border=0,
        escape=True,
    )


def charts_grid(charts: list[dict]) -> str:
    if not charts:
        return '<div class="muted">No charts available.</div>'
    cards = []
    for chart in charts:
        title = htmllib.escape(chart.get("title", "Chart"))
        filename = htmllib.escape(chart.get("filename", ""))
        caption = chart.get("caption")
        caption_html = f'<div class="muted">{htmllib.escape(caption)}</div>' if caption else ""
        cards.append(
            f"""
            <div class="card span-6">
              <div class="caption">{title}</div>
              <img src="{filename}" alt="{title}">
              {caption_html}
            </div>
            """
        )
    return f'<div class="grid">{"".join(cards)}</div>'


def kpi_cards(kpis: list[dict] | None) -> str:
    if not kpis:
        return '<div class="muted">No KPIs available.</div>'
    cards = []
    for kpi in kpis:
        label = htmllib.escape(str(kpi.get("label", "")))
        value = htmllib.escape(str(kpi.get("value", "")))
        cards.append(
            f"""
            <div class="card span-3">
              <div class="caption">{label}</div>
              <div class="kpi">{value}</div>
            </div>
            """
        )
    return f'<div class="grid">{"".join(cards)}</div>'


def exec_notes(notes: list[str]) -> str:
    if not notes:
        return '<div class="muted">No notes available.</div>'
    items = "".join(f"<li>{htmllib.escape(note)}</li>" for note in notes)
    return f"<ul>{items}</ul>"


def render_html_report(
    template_path: Path,
    output_path: Path,
    *,
    title: str,
    now: str,
    out_dir: Path,
    housekeeping: dict,
    room_usage: dict,
):
    template_text = template_path.read_text(encoding="utf-8")
    context = {
        "htmllib": htmllib,
        "title": title,
        "now": now,
        "out_dir": out_dir,
        "housekeeping": housekeeping,
        "room_usage": room_usage,
        "df_to_html_table": df_to_html_table,
        "charts_grid": charts_grid,
        "kpi_cards": kpi_cards,
        "exec_notes": exec_notes,
    }
    html_content = eval(f"f'''{template_text}'''", {"__builtins__": {}}, context)
    output_path.write_text(html_content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate housekeeping management visuals + summaries from CSV.")
    parser.add_argument(
    "--room-usage-csv",
    default="Room Usage.csv",
    help="Path to Room Usage CSV (default: Room Usage.csv)")

    parser.add_argument(
        "--housekeeping-csv",
        default="Housekeeping Change Log.csv",
        help="Path to Housekeeping Change Log CSV (default: Housekeeping Change Log.csv)")

    parser.add_argument(
        "--out",
        default=".",
        help="Output directory base (default: current folder)")

    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Top N for housekeepers/user charts (default: 10)")
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

    room_distribution = (
        df.groupby(["Username", "Room Number"], dropna=False)
          .size()
          .reset_index(name="room_actions")
    )
    room_totals = (
        room_distribution.groupby("Username", dropna=False)["room_actions"]
        .sum()
        .reset_index(name="total_actions")
    )
    room_distribution = room_distribution.merge(room_totals, on="Username", how="left")
    room_distribution["room_share"] = (
        room_distribution["room_actions"] / room_distribution["total_actions"].replace(0, pd.NA)
    )
    room_randomness = (
        room_distribution.assign(room_share_sq=room_distribution["room_share"] ** 2)
        .groupby("Username", dropna=False)["room_share_sq"]
        .sum()
        .reset_index(name="room_hhi")
    )
    room_randomness["room_randomness"] = 1 - room_randomness["room_hhi"]
    room_randomness = room_randomness.drop(columns=["room_hhi"])

    by_user = by_user.merge(room_randomness, on="Username", how="left")
    by_user["room_randomness"] = by_user["room_randomness"].fillna(0.0).round(3)
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
    uniqueness_by_user = uniqueness_by_user.merge(room_randomness, on="Username", how="left")
    uniqueness_by_user["room_uniqueness_rate"] = (
        uniqueness_by_user["unique_rooms"] / uniqueness_by_user["total_actions"].replace(0, pd.NA)
    ).fillna(0.0)
    uniqueness_by_user["room_randomness"] = uniqueness_by_user["room_randomness"].fillna(0.0)
    uniqueness_by_user["room_randomness_rank"] = (
        uniqueness_by_user["room_randomness"].rank(method="dense", ascending=False).astype(int)
    )
    uniqueness_by_user["rotation_quality"] = uniqueness_by_user["room_uniqueness_rate"].map(rotation_quality_label)
    uniqueness_by_user = uniqueness_by_user.sort_values(
        ["room_uniqueness_rate", "total_actions"],
        ascending=[True, False],
    )
    uniqueness_by_user["room_uniqueness_rate"] = uniqueness_by_user["room_uniqueness_rate"].round(3)
    uniqueness_by_user["room_randomness"] = uniqueness_by_user["room_randomness"].round(3)
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
    charts = []

    # 1) Daily volume
    if by_day is not None and len(by_day) > 0:
        fig = plt.figure()
        plt.plot(by_day["Day"], by_day["rows"], marker="o")
        plt.title("Daily volume (rows logged)")
        plt.xlabel("Day")
        plt.ylabel("Rows")
        plt.xticks(rotation=45, ha="right")
        daily_volume_path = out_dir / "daily_volume.png"
        plot_and_save(fig, daily_volume_path)
        charts.append({
            "title": "Daily volume (rows logged)",
            "filename": daily_volume_path.name,
        })

        # 2) Daily changes
        fig = plt.figure()
        plt.plot(by_day["Day"], by_day["changed"], marker="o")
        plt.title("Daily HSK status changes (Before ≠ After)")
        plt.xlabel("Day")
        plt.ylabel("Changed rows")
        plt.xticks(rotation=45, ha="right")
        daily_changes_path = out_dir / "daily_changes.png"
        plot_and_save(fig, daily_changes_path)
        charts.append({
            "title": "Daily HSK status changes (Before ≠ After)",
            "filename": daily_changes_path.name,
        })

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
        hsk_after_by_day_path = out_dir / "hsk_after_by_day.png"
        plot_and_save(fig, hsk_after_by_day_path)
        charts.append({
            "title": "HSK Status After by day (top statuses)",
            "filename": hsk_after_by_day_path.name,
        })

    # 4) Top housekeepers (After)
    top_n = max(1, int(args.top))
    hk_top = by_hk_after.head(top_n)
    fig = plt.figure()
    plt.barh(hk_top["Housekeeper After"].map(safe_title), hk_top["changed"])
    plt.title(f"Top {top_n} Housekeepers (by HSK changes, After)")
    plt.xlabel("Changed rows")
    plt.ylabel("Housekeeper After")
    plt.gca().invert_yaxis()
    top_housekeepers_path = out_dir / "top_housekeepers_after.png"
    plot_and_save(fig, top_housekeepers_path)
    charts.append({
        "title": f"Top {top_n} Housekeepers (by HSK changes, After)",
        "filename": top_housekeepers_path.name,
    })

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

    hsk_transition_heatmap_path = out_dir / "hsk_transition_heatmap.png"
    plot_and_save(fig, hsk_transition_heatmap_path)
    charts.append({
        "title": "HSK Status Transition Matrix (Before → After)",
        "filename": hsk_transition_heatmap_path.name,
    })

    transition.to_csv(out_dir / "summary_transition_matrix.csv")

    housekeeping_kpis = [
        {"label": "Total rows", "value": total_rows},
        {"label": "Unique rooms", "value": total_rooms_unique},
        {"label": "HSK changes", "value": changed_count},
        {"label": "Change rate", "value": f"{change_rate:.1%}"},
        {"label": "Date parse success", "value": f"{df['DateTime'].notna().mean():.1%}"},
    ]

    top_housekeeper = None
    if not by_hk_after.empty:
        top_housekeeper = by_hk_after.iloc[0]["Housekeeper After"]

    exec_note_items = [
        f"{changed_count} housekeeping status changes across {total_rows} records.",
        f"Change rate of {change_rate:.1%} indicates the share of records with updates.",
    ]
    if top_housekeeper:
        exec_note_items.append(f"Most frequent closer: {top_housekeeper}.")

    housekeeping_payload = {
        "kpis": housekeeping_kpis,
        "exec_notes": exec_note_items,
        "charts": charts,
        "by_day": by_day,
        "by_room_type": by_room_type,
        "by_hk_after": by_hk_after,
        "by_user": by_user,
        "transition_matrix": transition.reset_index(),
    }

    room_usage_payload = {
        "kpis": [],
        "exec_notes": [],
        "charts": [],
        "by_room_type": None,
        "top_rooms": None,
        "by_feature": None,
    }

    template_path = Path(__file__).resolve().parent / "Fixing up layout.html"
    if template_path.exists():
        report_path = out_dir / "report.html"
        render_html_report(
            template_path,
            report_path,
            title="Housekeeping Change Log Report",
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            out_dir=out_dir,
            housekeeping=housekeeping_payload,
            room_usage=room_usage_payload,
        )
        css_path = Path(__file__).resolve().parent / "Report.css"
        if css_path.exists():
            shutil.copy2(css_path, out_dir / css_path.name)

    # ---- Final message ----
    print(f"\n✅ Done. Report generated at:\n{out_dir.resolve()}\n")
    print("Files created:")
    for p in sorted(out_dir.iterdir()):
        print(f" - {p.name}")


if __name__ == "__main__":
    main()
