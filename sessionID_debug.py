import re
from playwright.sync_api import sync_playwright

BASE = "https://d301.msicloudpm.com"
REPORT_PAGE_URL = f"https://d301.msicloudpm.com/Reports/Reports.aspx?LSID=c12dd99d-5a06-4416-a435-3d8b56018d6c&UserId=6a302f32-0059-4c12-b4db-b76f5bc041a0"  # CHANGE THIS if the report viewer is on a different path

AXD_RE = re.compile(r"/Telerik\.ReportViewer\.axd", re.I)
IID_RE = re.compile(r"instanceID=([0-9a-f]{32})", re.I)

def main():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="pw_profile",
            headless=False,  # DEBUG MODE: WATCH IT
        )
        page = context.new_page()

        found = {"iid": None}

        def log_req(req):
            url = req.url
            if AXD_RE.search(url):
                print("[AXD REQ]", url)
            m = IID_RE.search(url)
            if m and not found["iid"]:
                found["iid"] = m.group(1)
                print("[FOUND instanceID]", found["iid"])

        page.on("request", log_req)

        page.goto(REPORT_PAGE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)  # give it time to load viewer traffic

        print("\n=== PAGE INFO ===")
        print("Final URL:", page.url)
        try:
            print("Title:", page.title())
        except Exception:
            print("Title: <could not read>")
        content = page.content().lower()
        print("Looks like login page:", any(x in content for x in ["login", "password", "sign in", "username"]))
        print("=================\n")

        if not found["iid"]:
            print("[!] No instanceID seen yet.")
            print("    If you see a login screen, log in manually in this window.")
            print("    Then navigate to the report page you normally use and wait ~10s.")
            input("Press Enter after you have navigated to the report viewer page...")
            page.wait_for_timeout(8000)

        # Try again after manual nav
        if not found["iid"]:
            print("[!] Still no instanceID. You're likely NOT on the report viewer page URL in REPORT_PAGE_URL.")
            print("    Copy the URL from the address bar right now and use it as REPORT_PAGE_URL.")
        else:
            print("[+] instanceID captured:", found["iid"])

        context.close()

if __name__ == "__main__":
    main()
