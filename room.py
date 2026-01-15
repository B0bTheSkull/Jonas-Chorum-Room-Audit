from pathlib import Path
from datetime import datetime
import argparse
import html as htmllib

import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------
# Helpers
# ----------------------------
def safe_str(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()

def coerce_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        format="%m/%d/%Y %H:%M",
        errors="coerce"
    )



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


def df_to_html_table(df: pd.DataFrame, max_rows: int = 50) -> str:
    """
    Convert DF to a clean HTML table.
    """
    if df is None or df.empty:
        return "<p class='muted'>No data available.</p>"

    view = df.head(max_rows).copy()
    # Escape everything to avoid weird HTML in cells
    for col in view.columns:
        view[col] = view[col].map(lambda v: htmllib.escape(safe_str(v)))

    # Build table manually for nicer control
    th = "".join(f"<th>{htmllib.escape(str(c))}</th>" for c in view.columns)
    rows = []
    for _, r in view.iterrows():
        tds = "".join(f"<td>{r[c]}</td>" for c in view.columns)
        rows.append(f"<tr>{tds}</tr>")
    tbody = "".join(rows)

    extra = ""
    if len(df) > max_rows:
        extra = f"<p class='muted'>Showing first {max_rows} of {len(df)} rows.</p>"

    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr>{th}</tr></thead>
        <tbody>{tbody}</tbody>
      </table>
      {extra}
    </div>
    """


def img_tag(filename: str, title: str = "") -> str:
    t = htmllib.escape(title)
    f = htmllib.escape(filename)
    cap = f"<div class='caption'>{t}</div>" if title else ""
    return f"""
    <div class="card">
      {cap}
      <img src="{f}" alt="{t}">
    </div>
    """


def tokenize_features(s: str) -> list[str]:
    """
    Split Orientation/Features into tokens.
    Handles commas, slashes, pipes, semicolons.
    """
    s = safe_str(s)
    if not s:
        return []
    for sep in ["|", "/", ";"]:
        s = s.replace(sep, ",")
    toks = [t.strip() for t in s.split(",")]
    toks = [t for t in toks if t]
    return toks

# ----------------------------
# Housekeeping Report
# ----------------------------
def build_housekeeping_section(df: pd.DataFrame, out_dir: Path, top_n: int):
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
        raise ValueError(f"Housekeeping CSV missing required columns: {missing}")

    # Normalize
    for c in required_cols:
        df[c] = df[c].map(safe_str)

    df["DateTime"] = coerce_datetime(df["Date"])
    df["Day"] = df["DateTime"].dt.date
    df["HSK_Changed"] = df["HSK Status Before"] != df["HSK Status After"]
    df["HSK_Transition"] = df["HSK Status Before"].fillna("") + " → " + df["HSK Status After"].fillna("")

    # KPIs
    total_rows = len(df)
    total_rooms_unique = df["Room Number"].nunique()
    changed_count = int(df["HSK_Changed"].sum())
    change_rate = (changed_count / total_rows) if total_rows else 0.0
    date_parse_success = float(df["DateTime"].notna().mean()) if total_rows else 0.0

    overall = pd.DataFrame([{
        "Total rows": total_rows,
        "Unique rooms": total_rooms_unique,
        "HSK status changes (count)": changed_count,
        "HSK status changes (rate)": round(change_rate, 4),
        "Date parse success rate": round(date_parse_success, 4),
    }])
    save_df(overall, out_dir / "summary_overall_housekeeping.csv")

    # By day (if parseable)
    by_day = None
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

    # By Housekeeper After
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

    # Transition matrix
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
    transition.to_csv(out_dir / "summary_hsk_transition_matrix.csv")

    # Charts
    chart_files = []

    if by_day is not None and len(by_day) > 0:
        # Daily volume
        fig = plt.figure()
        plt.plot(by_day["Day"], by_day["rows"], marker="o")
        plt.title("Daily volume (rows logged)")
        plt.xlabel("Day")
        plt.ylabel("Rows")
        plt.xticks(rotation=45, ha="right")
        fn = "daily_volume.png"
        plot_and_save(fig, out_dir / fn)
        chart_files.append((fn, "Daily volume (rows logged)"))

        # Daily changes
        fig = plt.figure()
        plt.plot(by_day["Day"], by_day["changed"], marker="o")
        plt.title("Daily HSK status changes (Before ≠ After)")
        plt.xlabel("Day")
        plt.ylabel("Changed rows")
        plt.xticks(rotation=45, ha="right")
        fn = "daily_changes.png"
        plot_and_save(fig, out_dir / fn)
        chart_files.append((fn, "Daily HSK status changes"))

        # HSK After distribution by day
        top_statuses = df["HSK Status After"].value_counts().head(8).index
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
        fn = "hsk_after_by_day.png"
        plot_and_save(fig, out_dir / fn)
        chart_files.append((fn, "HSK Status After by day (top statuses)"))

    # Top housekeepers by changes (After)
    top_n = max(1, int(top_n))
    hk_top = by_hk_after.head(top_n)
    fig = plt.figure()
    plt.barh(hk_top["Housekeeper After"], hk_top["changed"])
    plt.title(f"Top {top_n} Housekeepers (by HSK changes, After)")
    plt.xlabel("Changed rows")
    plt.ylabel("Housekeeper After")
    plt.gca().invert_yaxis()
    fn = "top_housekeepers_after.png"
    plot_and_save(fig, out_dir / fn)
    chart_files.append((fn, f"Top {top_n} Housekeepers (by changes, After)"))

    # Transition heatmap
    fig = plt.figure()
    mat = transition.values
    plt.imshow(mat, aspect="auto")
    plt.title("HSK Status Transition Matrix (Before → After)")
    plt.xlabel("HSK Status After")
    plt.ylabel("HSK Status Before")
    plt.xticks(range(len(transition.columns)), transition.columns, rotation=45, ha="right")
    plt.yticks(range(len(transition.index)), transition.index)

    if mat.size <= 400:
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                val = mat[i, j]
                if val != 0:
                    plt.text(j, i, str(val), ha="center", va="center")

    fn = "hsk_transition_heatmap.png"
    plot_and_save(fig, out_dir / fn)
    chart_files.append((fn, "HSK Status Transition Matrix (Before → After)"))

    # “Executive” bullet points (simple but useful)
    exec_notes = []
    if total_rows:
        exec_notes.append(f"{changed_count} of {total_rows} log entries changed HSK status ({change_rate:.1%}).")
    if len(by_room_type) > 0:
        top_rt = by_room_type.iloc[0]
        exec_notes.append(f"Most changed Room Type: {top_rt['Room Type']} ({int(top_rt['changed'])} changes).")
    if len(by_hk_after) > 0:
        top_hk = by_hk_after.iloc[0]
        exec_notes.append(f"Most closures by Housekeeper After: {top_hk['Housekeeper After']} ({int(top_hk['changed'])} changes).")
    if date_parse_success < 0.9:
        exec_notes.append(f"⚠ Date parsing success was {date_parse_success:.1%}. If charts look off, the Date column format is inconsistent.")

    section = {
        "kpis": overall,
        "by_day": by_day,
        "by_room_type": by_room_type,
        "by_hk_after": by_hk_after,
        "by_user": by_user,
        "transition_matrix": transition.reset_index(),
        "charts": chart_files,
        "exec_notes": exec_notes,
    }

    # ----------------------------
    # Uniqueness / rotation by Username
    # ----------------------------
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
        uniqueness_by_user["unique_rooms"] / uniqueness_by_user["total_actions"]
    ).round(3)

    def classify_rotation(x: float) -> str:
        if x < 0.20:
            return "Very Low (likely not rotating)"
        elif x < 0.40:
            return "Low"
        elif x < 0.60:
            return "Moderate"
        else:
            return "High (good rotation)"

    uniqueness_by_user["rotation_quality"] = uniqueness_by_user["room_uniqueness_rate"].apply(classify_rotation)

    # Sort: worst rotation first, but keep it meaningful by prioritizing people with real volume
    uniqueness_by_user = uniqueness_by_user.sort_values(
        ["room_uniqueness_rate", "total_actions"],
        ascending=[True, False]
    )

    # Save CSV
    save_df(uniqueness_by_user, out_dir / "username_room_rotation_uniqueness.csv")

    # Save chart (DON'T plt.show())
    fig = plt.figure()
    plt.scatter(
        uniqueness_by_user["total_actions"],
        uniqueness_by_user["room_uniqueness_rate"]
    )
    plt.xlabel("Total actions (rooms touched/logs)")
    plt.ylabel("Room uniqueness rate (unique_rooms / total_actions)")
    plt.title("Username room rotation efficiency")
    plt.axhline(0.60, linestyle="--")
    plt.axhline(0.40, linestyle="--")
    plt.axhline(0.20, linestyle="--")

    fn_uni = "username_room_rotation_scatter.png"
    plot_and_save(fig, out_dir / fn_uni)

    # Add to section so HTML can render it
    # Removed unnecessary reference to undefined variable 'housekeeping'
    section["uniqueness_chart"] = (fn_uni, "Room rotation efficiency (lower = repeatedly working same rooms)")

    
    return section


# ----------------------------
# Room Usage Report
# ----------------------------
def build_room_usage_section(df: pd.DataFrame, out_dir: Path, top_n: int):
    required_cols = ["Room Number", "Room Type", "Number of Nights", "Orientation/Features"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Room Usage CSV missing required columns: {missing}")

    for c in ["Room Number", "Room Type", "Orientation/Features"]:
        df[c] = df[c].map(safe_str)

    df["Number of Nights"] = pd.to_numeric(df["Number of Nights"], errors="coerce").fillna(0)

    total_rooms = df["Room Number"].nunique()
    total_nights = float(df["Number of Nights"].sum())
    avg_nights = (total_nights / total_rooms) if total_rooms else 0.0

    usage_kpis = pd.DataFrame([{
        "Unique rooms": total_rooms,
        "Total nights": int(total_nights),
        "Avg nights per room": round(avg_nights, 2),
    }])
    save_df(usage_kpis, out_dir / "summary_overall_room_usage.csv")

    by_room_type = (
        df.groupby("Room Type", dropna=False)
          .agg(
              rooms=("Room Number", "nunique"),
              total_nights=("Number of Nights", "sum"),
              avg_nights_per_room=("Number of Nights", "mean"),
          )
          .reset_index()
          .sort_values(["total_nights", "rooms"], ascending=[False, False])
    )
    by_room_type["avg_nights_per_room"] = by_room_type["avg_nights_per_room"].round(2)
    save_df(by_room_type, out_dir / "room_usage_by_room_type.csv")

    # Top rooms by nights
    top_n = max(1, int(top_n))
    top_rooms = (
        df.groupby(["Room Number", "Room Type"], dropna=False)["Number of Nights"]
          .sum()
          .reset_index()
          .sort_values("Number of Nights", ascending=False)
          .head(top_n)
    )
    save_df(top_rooms, out_dir / "room_usage_top_rooms.csv")

    # Feature rollup
    feat_rows = []
    for _, r in df.iterrows():
        toks = tokenize_features(r["Orientation/Features"])
        for t in toks:
            feat_rows.append((t, float(r["Number of Nights"])))

    if feat_rows:
        feats = pd.DataFrame(feat_rows, columns=["Feature", "Nights"])
        feat_summary = (
            feats.groupby("Feature")["Nights"]
                 .agg(total_nights="sum", mentions="size")
                 .reset_index()
                 .sort_values("total_nights", ascending=False)
        )
        feat_summary["total_nights"] = feat_summary["total_nights"].round(0).astype(int)
        save_df(feat_summary, out_dir / "room_usage_by_feature.csv")
    else:
        feat_summary = pd.DataFrame(columns=["Feature", "total_nights", "mentions"])
        save_df(feat_summary, out_dir / "room_usage_by_feature.csv")

    # Charts
    chart_files = []

    # Nights by room type (bar)
    if not by_room_type.empty:
        fig = plt.figure()
        plt.barh(by_room_type["Room Type"], by_room_type["total_nights"])
        plt.title("Total nights by Room Type")
        plt.xlabel("Total nights")
        plt.ylabel("Room Type")
        plt.gca().invert_yaxis()
        fn = "room_usage_nights_by_room_type.png"
        plot_and_save(fig, out_dir / fn)
        chart_files.append((fn, "Total nights by Room Type"))

    # Top rooms by nights (barh)
    if not top_rooms.empty:
        fig = plt.figure()
        labels = top_rooms.apply(lambda r: f"{r['Room Number']} ({r['Room Type']})", axis=1)
        plt.barh(labels, top_rooms["Number of Nights"])
        plt.title(f"Top {top_n} rooms by nights")
        plt.xlabel("Number of nights")
        plt.ylabel("Room")
        plt.gca().invert_yaxis()
        fn = "room_usage_top_rooms.png"
        plot_and_save(fig, out_dir / fn)
        chart_files.append((fn, f"Top {top_n} rooms by nights"))

    # Top features by nights
    if not feat_summary.empty:
        top_feats = feat_summary.head(top_n).copy()
        fig = plt.figure()
        plt.barh(top_feats["Feature"], top_feats["total_nights"])
        plt.title(f"Top {top_n} Orientation/Features (by total nights)")
        plt.xlabel("Total nights")
        plt.ylabel("Feature")
        plt.gca().invert_yaxis()
        fn = "room_usage_top_features.png"
        plot_and_save(fig, out_dir / fn)
        chart_files.append((fn, f"Top {top_n} Orientation/Features (by total nights)"))

    exec_notes = []
    if total_rooms:
        exec_notes.append(f"{int(total_nights)} total nights across {total_rooms} rooms (avg {avg_nights:.2f} nights/room).")
    if len(by_room_type) > 0:
        rt0 = by_room_type.iloc[0]
        exec_notes.append(f"Highest total nights Room Type: {rt0['Room Type']} ({int(rt0['total_nights'])} nights).")
    if len(top_rooms) > 0:
        tr0 = top_rooms.iloc[0]
        exec_notes.append(f"Most-used room: {tr0['Room Number']} ({tr0['Room Type']}) with {int(tr0['Number of Nights'])} nights.")

    section = {
        "kpis": usage_kpis,
        "by_room_type": by_room_type,
        "top_rooms": top_rooms,
        "by_feature": feat_summary,
        "charts": chart_files,
        "exec_notes": exec_notes,
    }
    # Remove undefined variables as they are not relevant in this function
    return section


# ----------------------------
# HTML Report Builder
# ----------------------------
def build_html_report(out_dir: Path, title: str, housekeeping: dict, room_usage: dict):
    css = """
:root{
  --bg:#0b0f14;
  --card:#121826;
  --card2:#0f1522;
  --text:#e6edf3;
  --muted:#9aa4b2;
  --line:rgba(230,237,243,.12);
  --accent:#7aa2f7;
  --good:#7ee787;
  --warn:#f2cc60;
}

*{ box-sizing:border-box; }

body{
  background:var(--bg);
  color:var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple Color Emoji","Segoe UI Emoji";
  margin:0;
  padding:28px;
  line-height:1.45;
}

.wrap{ max-width:1220px; margin:0 auto; }

h1{
  margin:0 0 6px;
  font-size:30px;
  letter-spacing:.2px;
}
h2{
  margin:34px 0 8px;
  font-size:22px;
}
h3{
  margin:20px 0 10px;
  font-size:15px;
  color:var(--accent);
  text-transform:uppercase;
  letter-spacing:.08em;
}

.sub{
  color:var(--muted);
  margin-bottom:18px;
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  align-items:center;
}

.grid{
  display:grid;
  gap:16px;
  grid-template-columns:repeat(12, 1fr);
  align-items:start;
}

/* IMPORTANT: cards should be normal block flow, not flex */
.card{
  display:flex;
  flex-direction: column;
  gap: 12px;         /* <- gives you the breathing room you want */
  padding: 16px;
}

.stack{
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.card.soft{
  background:linear-gradient(180deg, rgba(122,162,247,.10), rgba(18,24,38,0) 60%), var(--card);
}

.span-12{ grid-column:span 12; }
.span-8{ grid-column:span 8; }
.span-6{ grid-column:span 6; }
.span-4{ grid-column:span 4; }

.muted{ color:var(--muted); }
.caption{
  font-weight:650;
  margin:0 0 10px;
  font-size:14px;
}
p{ margin:0 0 10px; }
ul{ margin:8px 0 0 18px; }
li{ margin:6px 0; }

.pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid var(--line);
  background:rgba(122,162,247,.10);
  color:var(--text);
  font-size:12px;
}

/* KPI cards */
.kpi-wrap{
  display:grid;
  grid-template-columns:repeat(12,1fr);
  gap:16px;
}
.kpi-card{
  grid-column:span 4;
  background:var(--card2);
  border:1px solid var(--line);
  border-radius:18px;
  padding:14px 14px 12px;
  min-height:92px;
}
.kpi-label{
  color:var(--muted);
  font-size:12px;
  margin-bottom:6px;
}
.kpi{
  font-size:26px;
  font-weight:800;
  letter-spacing:.2px;
}

/* Tables */
.table-wrap{
  overflow:auto;
  border-radius:14px;
  border:1px solid var(--line);
}
table{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  font-size:13px;
  background:rgba(0,0,0,.08);
}
th, td{
  padding:10px 12px;
  border-bottom:1px solid var(--line);
  text-align:left;
  vertical-align:top;
  white-space:nowrap;
}
td{ white-space:normal; }
th{
  position:sticky;
  top:0;
  z-index:1;
  background:rgba(18,24,38,.92);
  backdrop-filter:blur(8px);
  font-weight:650;
}
tbody tr:nth-child(odd){ background:rgba(255,255,255,.02); }
tbody tr:hover{ background:rgba(122,162,247,.08); }

/* Images / charts */
img{
  width:100%;
  height:auto;
  border-radius:14px;
  border:1px solid var(--line);
  background:#0b0f14;
  display:block;
}

/* Section divider */
.hr{
  height:1px;
  background:var(--line);
  margin:24px 0;
}

/* Mobile */
@media (max-width: 920px){
  body{ padding:14px; }
  .span-6,.span-4,.span-8{ grid-column:span 12; }
  .kpi-card{ grid-column:span 12; }
  th, td{ white-space:normal; }
}
"""

    def rotation_callouts(uni_df: pd.DataFrame) -> str:
      if uni_df is None or uni_df.empty:
          return "<p class='muted'>No rotation data available.</p>"

      # Only flag people with enough volume to matter
      flagged = uni_df[uni_df["total_actions"] >= 10].copy()

      # Worst rotation first (low uniqueness, high volume)
      flagged = flagged.sort_values(
          ["room_uniqueness_rate", "total_actions"],
          ascending=[True, False]
      )
      uni_df = housekeeping.get("uniqueness_by_user")
      uni_chart = housekeeping.get("uniqueness_chart")

      uni_chart_html = (
          img_tag(uni_chart[0], uni_chart[1])
          if uni_chart and uni_chart[0]
          else "<p class='muted'>No rotation chart generated.</p>"
      )

      # Generate rotation callouts and table HTML
      rotation_callouts_html = rotation_callouts(uni_df)
      rotation_table_html = df_to_html_table(uni_df, max_rows=50) if uni_df is not None else "<p class='muted'>No rotation data available.</p>"

      # Return the generated HTML content
      return f"""
      <div class="grid">
        <div class="card span-12">
          {uni_chart_html}
        </div>
        <div class="card span-12">
          {rotation_callouts_html}
        </div>
        <div class="card span-12">
          {rotation_table_html}
        </div>
      </div>
      """


      worst = flagged.head(8)

      if worst.empty:
          return "<p class='muted'>No users met the minimum activity threshold for rotation analysis.</p>"

      items = []
      for _, r in worst.iterrows():
          items.append(
              f"<li><b>{htmllib.escape(str(r['Username']))}</b>: "
              f"{int(r['unique_rooms'])} unique rooms / {int(r['total_actions'])} actions "
              f"= <b>{float(r['room_uniqueness_rate']):.3f}</b> → "
              f"{htmllib.escape(str(r['rotation_quality']))}</li>"
          )
          return f"""
          <div class="card">
            <div class="caption">Rotation issues (likely not assigning unique rooms)</div>
            <p class="muted">
              Metric: <b>unique_rooms / total_actions</b>. Lower means repeatedly working the same rooms instead of rotating inventory.
              Only users with <b>10+ actions</b> are evaluated here.
            </p>
            <ul>
              {''.join(items)}
            </ul>
            <p class="muted">
              Quick read: <b>&lt;0.20</b> very low • <b>0.20–0.40</b> low • <b>0.40–0.60</b> moderate • <b>&gt;0.60</b> high.
            </p>
          </div>
          """

    def kpi_cards(df_kpi: pd.DataFrame) -> str:
        if df_kpi is None or df_kpi.empty:
            return "<p class='muted'>No KPIs available.</p>"

        row = df_kpi.iloc[0].to_dict()
        cards = []
        for k, v in row.items():
            cards.append(f"""
            <div class="kpi-card">
            <div class="kpi-label">{htmllib.escape(str(k))}</div>
            <div class="kpi">{htmllib.escape(str(v))}</div>
            </div>
            """)
        return "<div class='kpi-wrap'>" + "\n".join(cards) + "</div>"


    def exec_notes(notes: list[str]) -> str:
        if not notes:
            return "<p class='muted'>No notable items.</p>"
        lis = "\n".join(f"<li>{htmllib.escape(n)}</li>" for n in notes)
        return f"<ul>{lis}</ul>"

    def charts_grid(charts: list[tuple[str, str]]) -> str:
        if not charts:
            return "<p class='muted'>No charts generated.</p>"
        blocks = []
        for fn, cap in charts:
            blocks.append(f"<div class='span-6'>{img_tag(fn, cap)}</div>")
        return "<div class='grid'>" + "\n".join(blocks) + "</div>"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>{htmllib.escape(title)}</title>
      <style>{css}</style>
    </head>
    <body>
      <div class="wrap">
        <h1>{htmllib.escape(title)}</h1>
        <div class="sub">Generated {htmllib.escape(now)} • Folder: <span class="pill">{htmllib.escape(out_dir.name)}</span></div>

        <div class="card soft">
          <div class="caption">What this report is</div>
          <div class="muted">
            A clean snapshot of housekeeping status changes and room usage.
            It focuses on volume, real changes (Before ≠ After), who closed work, and what room types/features are getting used.
          </div>
        </div>

        <h2>Housekeeping Change Log</h2>
        <h3>KPIs</h3>
        {kpi_cards(housekeeping.get("kpis"))}

        <div class="card">
          <div class="caption">Executive notes</div>
          {exec_notes(housekeeping.get("exec_notes", []))}
        </div>

        <h3>Charts</h3>
        {charts_grid(housekeeping.get("charts", []))}

        <h3>Summaries</h3>
        <div class="grid stack">
          <div class="card span-12">
            <div class="caption">By day</div>
            {df_to_html_table(housekeeping.get("by_day"))}
          </div>
          <div class="card span-12">
            <div class="caption">By room type</div>
            {df_to_html_table(housekeeping.get("by_room_type"))}
          </div>
          <div class="card span-12">
            <div class="caption">By housekeeper (After)</div>
            {df_to_html_table(housekeeping.get("by_hk_after"))}
          </div>
          <div class="card span-12">
            <div class="caption">By username</div>
            {df_to_html_table(housekeeping.get("by_user"))}
          </div>
          <div class="card span-12">
            <div class="caption">HSK transition matrix (Before → After)</div>
            {df_to_html_table(housekeeping.get("transition_matrix"))}
          </div>
        </div>

        <div class="hr stack"></div>

        <h2>Room Usage</h2>
        <h3>KPIs</h3>
        {kpi_cards(room_usage.get("kpis"))}

        <div class="card">
          <div class="caption">Executive notes</div>
          {exec_notes(room_usage.get("exec_notes", []))}
        </div>

        <h3>Charts</h3>
        {charts_grid(room_usage.get("charts", []))}

        <h3>Summaries</h3>
        <div class="grid">
          <div class="card span-12">
            <div class="caption">Nights by room type</div>
            {df_to_html_table(room_usage.get("by_room_type"))}
          </div>
          <div class="card span-12">
            <div class="caption">Top rooms by nights</div>
            {df_to_html_table(room_usage.get("top_rooms"))}
          </div>
          <div class="card span-12">
            <div class="caption">Orientation/Features rollup</div>
            {df_to_html_table(room_usage.get("by_feature"))}
          </div>
        </div>

        <div class="card">
          <div class="caption">Notes</div>
          <ul>
            <li>All tables are capped for display; full CSV summaries are in the same folder.</li>
            <li>If the housekeeping “By day” section is empty, your Date column is too inconsistent to parse — fix the format and rerun.</li>
          </ul>
        <div class="hr"></div>

          <h3>Room Rotation by Username</h3>

          <div class="card">
            <div class="caption">How to read this</div>
            <p class="muted">
              This measures whether a user is repeatedly touching the same rooms instead of spreading work across inventory.
              Metric: <b>unique_rooms / total_actions</b>. Lower values = less rotation (more repetition).
            </p>
          </div>

          <div class="grid">
            <div class="span-12">
              {{UNI_CHART_HTML}}
            </div>
          </div>

          {{ROTATION_CALLOUTS_HTML}}

          <div class="card">
            <div class="caption">Rotation table (all users)</div>
            {{}}
          </div>
          <div class="card">
            <div class="caption">How to read this</div>
            <p class="muted">
              Metric: <b>unique_rooms / total_actions</b>. Lower values = less rotation (more repetition).
              Only users with <b>10+ actions</b> should be considered “real signals.”
            </p>
          </div>

          <div class="grid">
            <div class="card span-12">
              {{uni_chart_html}}
            </div>
          </div>

          {{rotation_callouts_html}}

          <div class="card">
            <div class="caption">Rotation table (all users)</div>
            {{rotation_table_html}}
          </div>
      </div>
    </body>
    </html>
    """

    (out_dir / "report.html").write_text(html, encoding="utf-8")


# ----------------------------
# Main
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate management-ready housekeeping + room-usage report (HTML + charts + CSV summaries).")
    parser.add_argument("--housekeeping", default="Housekeeping Change Log.csv", help="Housekeeping CSV filename/path")
    parser.add_argument("--usage", default="Room Usage.csv", help="Room Usage CSV filename/path")
    parser.add_argument("--out", default=".", help="Output directory base (default: current folder)")
    parser.add_argument("--top", type=int, default=10, help="Top N used for some charts/tables (default: 10)")
    args = parser.parse_args()

    hk_path = Path(args.housekeeping)
    usage_path = Path(args.usage)
    out_base = Path(args.out)

    if not hk_path.exists():
        raise FileNotFoundError(f"Housekeeping CSV not found: {hk_path}")
    if not usage_path.exists():
        raise FileNotFoundError(f"Room Usage CSV not found: {usage_path}")

    out_dir = ensure_output_dir(out_base)

    # Load
    hk_df = pd.read_csv(hk_path)
    usage_df = pd.read_csv(usage_path)

    # Build sections
    housekeeping = build_housekeeping_section(hk_df, out_dir, top_n=args.top)
    room_usage = build_room_usage_section(usage_df, out_dir, top_n=args.top)

    # Build HTML report
    title = "Operations Report — Housekeeping + Room Usage"
    build_html_report(out_dir, title, housekeeping, room_usage)

    print(f"\n✅ Done. Report generated at:\n{out_dir.resolve()}\n")
    print("Open: report.html")
    print("Files created:")
    for p in sorted(out_dir.iterdir()):
        print(f" - {p.name}")


if __name__ == "__main__":
    main()
