from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import tempfile


def compute_neosca_metrics(text_content: str, timeout: int = 1000) -> dict[str, float | str]:
    if not text_content.strip():
        return {}

    tmp_dir = tempfile.mkdtemp()
    txt_path = os.path.join(tmp_dir, "sample.txt")
    csv_path = os.path.join(tmp_dir, "result.csv")

    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text_content)

        subprocess.run(
            [sys.executable, "-m", "neosca", txt_path, "-o", csv_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

        if not os.path.exists(csv_path):
            print("NeoSCA did not generate a result file.")
            return {}

        with open(csv_path, "r", encoding="utf-8") as f:
            row = next(csv.DictReader(f))

        result: dict[str, float | str] = {}
        for key, value in row.items():
            if key == "Filename":
                continue
            try:
                result[key] = round(float(value), 4)
            except (ValueError, TypeError):
                result[key] = value
        return result

    except subprocess.TimeoutExpired:
        print("NeoSCA call timed out.")
        return {}
    except subprocess.CalledProcessError as exc:
        print(f"NeoSCA call failed: {exc.stderr}")
        return {}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)