import pandas as pd
import re
from pathlib import Path

def anonymize_name(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)

    # handle "Last, First"
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            s = parts[1] + " " + parts[0]

    parts = s.split(" ")
    if len(parts) == 1:
        return parts[0]  # single token
    return f"{parts[0]} {parts[-1][0].upper()}."

def clean_housekeeping_csv(input_csv: str, output_csv: str):
    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)

    # 1) normalize headers + strip whitespace in every cell
    df.columns = df.columns.str.strip()
    df = df.applymap(lambda v: v.strip() if isinstance(v, str) else v)

    # 2) anonymize the columns you told me exist
    for col in ["Housekeeper Before", "Housekeeper After", "Username"]:
        if col in df.columns:
            df[col] = df[col].apply(anonymize_name)

    # 3) optional: standardize dates if you have a Date column
    # (uncomment and rename if your column differs)
    # if "Date" in df.columns:
    #     df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # 4) save cleaned CSV
    df.to_csv(output_csv, index=False)
    return df

if __name__ == "__main__":
    clean_housekeeping_csv(
        "Housekeeping Change Log.csv",
        "Housekeeping Change Log - CLEAN.csv"
    )
