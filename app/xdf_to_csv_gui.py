"""
ARL XDF to CSV Converter GUI
Double-click this file, or run Run_XDF_Converter.bat from the project root.

Purpose:
- Select a LabRecorder .xdf file
- Export each LSL stream to a separate CSV
- Generate stream_summary.csv and stream_report.json
"""

from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List

try:
    import pandas as pd
    import pyxdf
except Exception as exc:  # shown in GUI after Tk starts
    pd = None
    pyxdf = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def safe_name(name: str) -> str:
    name = name.strip() or "unnamed_stream"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def first(value: Any, default: Any = "") -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return value if value is not None else default


def get_channel_labels(stream: Dict[str, Any], channel_count: int) -> List[str]:
    info = stream.get("info", {})
    labels: List[str] = []
    try:
        channels = info.get("desc", [{}])[0].get("channels", [{}])[0].get("channel", [])
        if isinstance(channels, dict):
            channels = [channels]
        for ch in channels:
            label = first(ch.get("label", []), "") if isinstance(ch, dict) else ""
            labels.append(str(label).strip())
    except Exception:
        labels = []

    if len(labels) != channel_count or any(not x for x in labels):
        labels = [f"ch_{i+1:02d}" for i in range(channel_count)]

    # Ensure unique column names
    seen = {}
    unique = []
    for label in labels:
        base = safe_name(label)
        seen[base] = seen.get(base, 0) + 1
        unique.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return unique


def stream_to_dataframe(stream: Dict[str, Any]) -> pd.DataFrame:
    timestamps = stream.get("time_stamps", [])
    samples = stream.get("time_series", [])

    # pyxdf may return marker streams as list of lists of strings, numeric arrays, or empty arrays.
    df = pd.DataFrame(samples)
    if df.shape[1] == 0:
        df = pd.DataFrame(index=range(len(timestamps)))

    labels = get_channel_labels(stream, df.shape[1])
    if len(labels) == df.shape[1]:
        df.columns = labels

    df.insert(0, "lsl_timestamp", timestamps)
    return df


def convert_xdf(xdf_path: Path, output_dir: Path) -> Dict[str, Any]:
    if pyxdf is None or pd is None:
        raise RuntimeError(
            "Missing required packages. Install them with: pip install pyxdf pandas"
        )
    if not xdf_path.exists():
        raise FileNotFoundError(f"XDF file not found: {xdf_path}")
    if xdf_path.suffix.lower() != ".xdf":
        raise ValueError("Please select a real .xdf file, not a folder.")

    output_dir.mkdir(parents=True, exist_ok=True)
    streams, header = pyxdf.load_xdf(str(xdf_path))

    summary_rows = []
    exported_files = []

    for idx, stream in enumerate(streams, start=1):
        info = stream.get("info", {})
        name = str(first(info.get("name", []), f"stream_{idx:02d}"))
        stream_type = str(first(info.get("type", []), ""))
        nominal_srate = str(first(info.get("nominal_srate", []), ""))
        channel_count = int(float(first(info.get("channel_count", []), 0) or 0))
        timestamps = stream.get("time_stamps", [])

        df = stream_to_dataframe(stream)
        filename = f"{idx:02d}_{safe_name(name)}.csv"
        csv_path = output_dir / filename
        df.to_csv(csv_path, index=False)
        exported_files.append(str(csv_path))

        duration = None
        if len(timestamps) >= 2:
            duration = float(timestamps[-1] - timestamps[0])

        summary_rows.append({
            "index": idx,
            "name": name,
            "type": stream_type,
            "nominal_srate": nominal_srate,
            "channel_count": channel_count if channel_count else max(df.shape[1] - 1, 0),
            "samples": int(len(df)),
            "duration_seconds": duration,
            "csv_file": filename,
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(output_dir / "stream_summary.csv", index=False)

    report = {
        "input_xdf": str(xdf_path),
        "output_dir": str(output_dir),
        "stream_count": len(streams),
        "streams": summary_rows,
        "xdf_header": header,
        "status": "PASS" if len(streams) > 0 else "WARN_NO_STREAMS",
    }
    with open(output_dir / "stream_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    return report


class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ARL XDF to CSV Converter")
        self.geometry("760x520")
        self.minsize(700, 460)

        self.xdf_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready. Select an XDF file.")

        self._build_ui()

        if IMPORT_ERROR is not None:
            messagebox.showwarning(
                "Missing Packages",
                "pyxdf and/or pandas could not be imported.\n\n"
                "Install them with:\n\npip install pyxdf pandas\n\n"
                f"Details: {IMPORT_ERROR}",
            )

    def _build_ui(self):
        pad = {"padx": 12, "pady": 8}

        title = ttk.Label(self, text="ARL XDF to CSV Converter", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w", padx=14, pady=(14, 4))

        subtitle = ttk.Label(self, text="Select a LabRecorder .xdf file and export each LSL stream as a CSV.")
        subtitle.pack(anchor="w", padx=14, pady=(0, 8))

        frame = ttk.Frame(self)
        frame.pack(fill="x", **pad)

        ttk.Label(frame, text="Input XDF file").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.xdf_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.browse_xdf).grid(row=1, column=1)

        ttk.Label(frame, text="Output folder").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(frame, textvariable=self.out_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.browse_output).grid(row=3, column=1)
        frame.columnconfigure(0, weight=1)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=12, pady=4)
        ttk.Button(button_frame, text="Convert XDF to CSV", command=self.run_conversion).pack(side="left")
        ttk.Button(button_frame, text="Open Output Folder", command=self.open_output).pack(side="left", padx=8)

        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", padx=14, pady=(8, 4))

        self.log = tk.Text(self, height=16, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.write_log("Ready.\n")

    def browse_xdf(self):
        path = filedialog.askopenfilename(
            title="Select XDF file",
            filetypes=[("XDF files", "*.xdf"), ("All files", "*.*")],
        )
        if path:
            self.xdf_var.set(path)
            default_out = str(Path(path).with_suffix("")) + "_csv"
            self.out_var.set(default_out)
            self.write_log(f"Selected XDF: {path}\n")

    def browse_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.out_var.set(path)

    def write_log(self, text: str):
        self.log.insert("end", text)
        self.log.see("end")
        self.update_idletasks()

    def run_conversion(self):
        xdf_text = self.xdf_var.get().strip().strip('"')
        out_text = self.out_var.get().strip().strip('"')

        if not xdf_text:
            messagebox.showerror("Missing XDF", "Please select an .xdf file.")
            return
        if not out_text:
            messagebox.showerror("Missing Output Folder", "Please select an output folder.")
            return

        xdf_path = Path(xdf_text)
        output_dir = Path(out_text)

        try:
            self.status_var.set("Converting...")
            self.write_log("\nStarting conversion...\n")
            report = convert_xdf(xdf_path, output_dir)
            self.write_log(f"Streams found: {report['stream_count']}\n")
            for s in report["streams"]:
                self.write_log(f"✓ {s['name']} -> {s['csv_file']} ({s['samples']} samples)\n")
            self.write_log(f"\nSaved summary: {output_dir / 'stream_summary.csv'}\n")
            self.write_log(f"Saved report: {output_dir / 'stream_report.json'}\n")
            self.status_var.set("Conversion complete.")
            messagebox.showinfo("Conversion Complete", f"CSV files saved to:\n{output_dir}")
        except Exception as exc:
            self.status_var.set("Conversion failed.")
            self.write_log("\nERROR:\n")
            self.write_log(str(exc) + "\n")
            self.write_log(traceback.format_exc() + "\n")
            messagebox.showerror("Conversion Failed", str(exc))

    def open_output(self):
        out_text = self.out_var.get().strip().strip('"')
        if not out_text:
            return
        path = Path(out_text)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))


if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()
