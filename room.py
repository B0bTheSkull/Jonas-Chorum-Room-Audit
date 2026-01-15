from collections import defaultdict
import sys


def build_html_report(out_dir: Path, title: str, housekeeping: dict, room_usage: dict):
  css = """
  /* CSS content remains unchanged */
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

  def rotation_callouts(uni_df: pd.DataFrame) -> str:
    if uni_df is None or uni_df.empty:
      return "<p class='muted'>No rotation data available.</p>"

    flagged = uni_df[uni_df["total_actions"] >= 10].copy()
    flagged = flagged.sort_values(
      ["room_uniqueness_rate", "total_actions"],
      ascending=[True, False]
    )

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

  now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  rotation_sources = [housekeeping, room_usage]
  uni_chart = next(
    (source.get("uniqueness_chart") for source in rotation_sources if source),
    None,
  )
  uni_chart_html = (
    img_tag(uni_chart[0], uni_chart[1])
    if uni_chart and uni_chart[0]
    else "<p class='muted'>No rotation chart generated.</p>"
  )

  uniqueness_by_user = next(
    (source.get("uniqueness_by_user") for source in rotation_sources if source),
    None,
  )
  rotation_callouts_html = rotation_callouts(uniqueness_by_user) or ""
  rotation_table_html = df_to_html_table(uniqueness_by_user, max_rows=50) or ""

  housekeeping_kpis_html = kpi_cards(housekeeping.get("kpis"))
  housekeeping_exec_notes_html = exec_notes(housekeeping.get("exec_notes", []))
  housekeeping_charts_html = charts_grid(housekeeping.get("charts", []))
  housekeeping_by_day_html = df_to_html_table(housekeeping.get("by_day"))
  housekeeping_by_room_type_html = df_to_html_table(housekeeping.get("by_room_type"))
  housekeeping_by_hk_after_html = df_to_html_table(housekeeping.get("by_hk_after"))
  housekeeping_by_user_html = df_to_html_table(housekeeping.get("by_user"))
  housekeeping_transition_matrix_html = df_to_html_table(
    housekeeping.get("transition_matrix")
  )

  room_usage_kpis_html = kpi_cards(room_usage.get("kpis"))
  room_usage_exec_notes_html = exec_notes(room_usage.get("exec_notes", []))
  room_usage_charts_html = charts_grid(room_usage.get("charts", []))
  room_usage_by_room_type_html = df_to_html_table(room_usage.get("by_room_type"))
  room_usage_top_rooms_html = df_to_html_table(room_usage.get("top_rooms"))
  room_usage_by_feature_html = df_to_html_table(room_usage.get("by_feature"))

  rotation_placeholders = {
    "uni_chart_html": uni_chart_html or "",
    "rotation_callouts_html": rotation_callouts_html or "",
    "rotation_table_html": rotation_table_html or "",
  }

  html_template = """
  <!doctype html>
  <html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>{css}</style>
  </head>
  <body>
    <div class="wrap">
    <h1>{title}</h1>
    <div class="sub">Generated {now} • Folder: <span class="pill">{out_dir_name}</span></div>

    <div class="card soft">
      <div class="caption">What this report is</div>
      <div class="muted">
      A clean snapshot of housekeeping status changes and room usage.
      It focuses on volume, real changes (Before ≠ After), who closed work, and what room types/features are getting used.
      </div>
    </div>

    <h2>Housekeeping Change Log</h2>
    <h3>KPIs</h3>
    {housekeeping_kpis_html}

    <div class="card">
      <div class="caption">Executive notes</div>
      {housekeeping_exec_notes_html}
    </div>

    <h3>Charts</h3>
    {housekeeping_charts_html}

    <h3>Summaries</h3>
    <div class="grid stack">
      <div class="card span-12">
      <div class="caption">By day</div>
      {housekeeping_by_day_html}
      </div>
      <div class="card span-12">
      <div class="caption">By room type</div>
      {housekeeping_by_room_type_html}
      </div>
      <div class="card span-12">
      <div class="caption">By housekeeper (After)</div>
      {housekeeping_by_hk_after_html}
      </div>
      <div class="card span-12">
      <div class="caption">By username</div>
      {housekeeping_by_user_html}
      </div>
      <div class="card span-12">
      <div class="caption">HSK transition matrix (Before → After)</div>
      {housekeeping_transition_matrix_html}
      </div>
    </div>

    <div class="hr stack"></div>

    <h2>Room Usage</h2>
    <h3>KPIs</h3>
    {room_usage_kpis_html}

    <div class="card">
      <div class="caption">Executive notes</div>
      {room_usage_exec_notes_html}
    </div>

    <h3>Charts</h3>
    {room_usage_charts_html}

    <h3>Summaries</h3>
    <div class="grid">
      <div class="card span-12">
      <div class="caption">Nights by room type</div>
      {room_usage_by_room_type_html}
      </div>
      <div class="card span-12">
      <div class="caption">Top rooms by nights</div>
      {room_usage_top_rooms_html}
      </div>
      <div class="card span-12">
      <div class="caption">Orientation/Features rollup</div>
      {room_usage_by_feature_html}
      </div>
    </div>

    <div class="hr"></div>

    <h3>Room Rotation by Username</h3>
    <div class="card">
      <div class="caption">How to read this</div>
      <p class="muted">
        Metric: <b>unique_rooms / total_actions</b>. Lower values = less rotation (more repetition).
        Only users with <b>10+ actions</b> should be considered “real signals.”
      </p>
    </div>
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
    </div>
  </body>
  </html>
  """

  html = html_template.format_map(
    defaultdict(
      str,
      {
        "title": htmllib.escape(title),
        "now": htmllib.escape(now),
        "out_dir_name": htmllib.escape(out_dir.name),
        "css": css,
        "housekeeping_kpis_html": housekeeping_kpis_html,
        "housekeeping_exec_notes_html": housekeeping_exec_notes_html,
        "housekeeping_charts_html": housekeeping_charts_html,
        "housekeeping_by_day_html": housekeeping_by_day_html,
        "housekeeping_by_room_type_html": housekeeping_by_room_type_html,
        "housekeeping_by_hk_after_html": housekeeping_by_hk_after_html,
        "housekeeping_by_user_html": housekeeping_by_user_html,
        "housekeeping_transition_matrix_html": housekeeping_transition_matrix_html,
        "room_usage_kpis_html": room_usage_kpis_html,
        "room_usage_exec_notes_html": room_usage_exec_notes_html,
        "room_usage_charts_html": room_usage_charts_html,
        "room_usage_by_room_type_html": room_usage_by_room_type_html,
        "room_usage_top_rooms_html": room_usage_top_rooms_html,
        "room_usage_by_feature_html": room_usage_by_feature_html,
        **rotation_placeholders,
      },
    )
  )
  (out_dir / "report.html").write_text(html, encoding="utf-8")


def _template_self_test() -> None:
  template = "{uni_chart_html}{rotation_callouts_html}{rotation_table_html}"
  rendered = template.format_map(
    defaultdict(
      str,
      {
        "uni_chart_html": "chart",
        "rotation_callouts_html": "callouts",
        "rotation_table_html": "table",
      },
    )
  )
  assert "chart" in rendered
  assert "callouts" in rendered
  assert "table" in rendered


if __name__ == "__main__":
  if "--test-template" in sys.argv:
    _template_self_test()
