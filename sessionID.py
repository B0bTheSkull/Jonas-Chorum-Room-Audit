import re
import datetime as dt
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://d301.msicloudpm.com/Reports/Reports.aspx"
REPORT_PAGE_URL = "https://d301.msicloudpm.com/Reports/Reports.aspx?LSID=c12dd99d-5a06-4416-a435-3d8b56018d6c&UserId=6a302f32-0059-4c12-b4db-b76f5bc041a0"   # <-- change if your report viewer is on a deeper path

OUT_DIR = Path("exports")
OUT_DIR.mkdir(exist_ok=True)

INSTANCE_RE = re.compile(r"instanceID=([0-9a-f]{32})", re.I)

def main():
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = OUT_DIR / f"report_{ts}.csv"

    with sync_playwright() as p:
        # Persistent context stores cookies/login in ./pw_profile
        context = p.chromium.launch_persistent_context(
            user_data_dir="pw_profile",
            headless=False, # Change to True to run headless
        )
        page = context.new_page()

        instance_id = {"value": None}

        def on_request(req):
            m = INSTANCE_RE.search(req.url)
            if m and instance_id["value"] is None:
                instance_id["value"] = m.group(1)

        page.on("request", on_request)

        page.goto(REPORT_PAGE_URL, wait_until="networkidle")

        # Give Telerik a moment to initialize and fire Parameters/Document calls
        page.wait_for_timeout(50000)

        if not instance_id["value"]:
            # If you hit this, you're probably not on the report viewer page
            # or you're not logged in in the stored profile.
            raise RuntimeError(
                "No instanceID seen in network traffic. "
                "Open pw_profile once in headed mode to log in, "
                "and/or set REPORT_PAGE_URL to the actual report viewer page."
            )

        iid = instance_id["value"]
        export_url = f"{BASE}/Telerik.ReportViewer.axd?instanceID={iid}&optype=Export&ExportFormat=CSV"

        # Download via browser context so cookies/auth are applied
        with page.expect_download() as dl_info:
            page.goto(export_url)

        download = dl_info.value
        download.save_as(out_path)

        print("Saved:", out_path)

        context.close()

if __name__ == "__main__":
    main()
