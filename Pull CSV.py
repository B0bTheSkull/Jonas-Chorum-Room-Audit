import datetime as dt
from pathlib import Path
import requests

URL = "https://d301.msicloudpm.com/Telerik.ReportViewer.axd?instanceID=da2335bb204042dabd499cbd0f7bb80d&optype=Export&ExportFormat=CSV"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept": "text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://d301.msicloudpm.com/",
    # Paste EXACTLY what comes after `Cookie:` from your curl:
    "Cookie": "MSICloudPM=HotelCode=UNILOG&UserName=CameronS&StationId=7ade47c1-ac06-4b01-8b48-b83f1c3ec63b&Toaster=http://UNILOGCCP/CloudPMOffline/Login.aspx&ChangePassword=false; showLastClean=true; ASP.NET_SessionId=1lrb15nyxvuaety3ticxgjcf; .ASPXAUTH=916EF2CE4705F0C055AF0DA8428CD3BFB1B642013A0C945E72455B32BC493FE98F6E42F09E406D4E5961EB3D5C8261FACFB78ED3556C9BBBBC6460861CD5532983C6A44B35055FCE03C186C226A9F6FAF2627EACE653E36C33DC87DE4CEB23B5",
}

def main():
    out_dir = Path("exports")
    out_dir.mkdir(exist_ok=True)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"telerik_export_{ts}.csv"

    r = requests.get(URL, headers=HEADERS, timeout=60, allow_redirects=True)
    print("[*] Status:", r.status_code)
    print("[*] Content-Type:", r.headers.get("Content-Type"))

    # If you got HTML, you’re not authenticated or instanceID expired
    sample = (r.text[:500] if isinstance(r.text, str) else "")  # requests always provides text
    if "<html" in sample.lower() or "<!doctype" in sample.lower():
        print("[!] Got HTML instead of CSV. Likely logged out or instanceID invalid.")
        # Save it anyway for inspection
        html_path = out_dir / f"telerik_export_{ts}.html"
        html_path.write_text(r.text, encoding="utf-8", errors="replace")
        print("[*] Saved HTML to:", html_path)
        return

    # Otherwise, save bytes as CSV
    out_path.write_bytes(r.content)
    print("[+] Saved CSV to:", out_path, f"({len(r.content):,} bytes)")

    # Quick preview
    try:
        print("\n=== Preview ===")
        print(r.content[:1000].decode("utf-8", errors="replace"))
    except Exception:
        pass

if __name__ == "__main__":
    main()
