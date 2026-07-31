import os
import re
import csv
import tempfile
import subprocess
import shutil


def extract_text_from_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines).strip()


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(https?://\S+|ftp://\S+|www\.\S+)", " ", text)
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_neosca_metrics(text_content: str) -> dict:
    if not text_content.strip():
        return {}

    tmp_dir = tempfile.mkdtemp()
    txt_path = os.path.join(tmp_dir, "sample.txt")
    csv_path = os.path.join(tmp_dir, "result.csv")

    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text_content)

        subprocess.run(
            ["python", "-m", "neosca", txt_path, "-o", csv_path],
            capture_output=True,
            text=True,
            timeout=1000,
            check=True,
        )

        if not os.path.exists(csv_path):
            print("NeoSCA did not generate a result file.")
            return {}

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

        result = {}
        for k, v in row.items():
            if k == "Filename":
                continue
            try:
                result[k] = round(float(v), 4)
            except (ValueError, TypeError):
                result[k] = v
        return result

    except subprocess.TimeoutExpired:
        print("NeoSCA call timed out.")
        return {}
    except subprocess.CalledProcessError as e:
        print(f"NeoSCA call failed: {e.stderr}")
        return {}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


NEOSCA_FIELDS = [
    "MLS", "MLT", "MLC", "C/S", "VP/T", "C/T", "DC/C", "DC/T",
    "T/S", "CT/T", "CP/T", "CP/C", "CN/T", "CN/C",
    "W", "S", "VP", "C", "T", "DC", "CT", "CP", "CN"
]


def process_category_folder(category_path: str, output_dir: str):
    if not os.path.exists(category_path):
        print(f"Folder path {category_path} does not exist, skipping to the next folder.")
        return
    category_name = os.path.basename(category_path)
    output_csv = os.path.join(output_dir, f"{category_name}_NeoSCA.csv")

    txt_files_all = [f for f in os.listdir(category_path) if f.endswith(".txt")]
    processed_files = set()
    existing_fieldnames = None

    if os.path.exists(output_csv):
        try:
            with open(output_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                existing_fieldnames = reader.fieldnames
                for row in reader:
                    processed_files.add(row["filename"])
            print(f"Found existing progress file, {len(processed_files)} files already processed.")
        except Exception as e:
            print(f"Error reading progress file, restarting: {e}")
            processed_files = set()
            existing_fieldnames = None

    txt_files = [f for f in txt_files_all if f not in processed_files]
    if not txt_files:
        print("All files have been processed.")
        return

    if existing_fieldnames is None:
        fieldnames = ["filename"] + NEOSCA_FIELDS
        write_header = True
        file_mode = "w"
    else:
        fieldnames = existing_fieldnames
        write_header = False
        file_mode = "a"

    with open(output_csv, file_mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, restval="")
        if write_header:
            writer.writeheader()

        for txt_file in txt_files:
            file_path = os.path.join(category_path, txt_file)
            text_content = clean_text(extract_text_from_file(file_path))
            if not text_content:
                print(f"{txt_file}: text is empty, skipping")
                continue
            print(f"{txt_file}: {text_content[:30]}...")

            neosca_metrics = compute_neosca_metrics(text_content)
            if not neosca_metrics:
                print(f"{txt_file}: NeoSCA calculation failed, skipping")
                continue

            row = {"filename": txt_file}
            row.update(neosca_metrics)

            filtered_row = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(filtered_row)
            csvfile.flush()
            print(f"  Write completed: {txt_file}")

    print(f"NeoSCA metrics for folder {category_name} saved to {output_csv}")


def main():
    print("\nStarting NeoSCA metric calculation...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    source_dir = os.path.join(base_dir, "source")
    result_dir = os.path.join(base_dir, "result")
    os.makedirs(result_dir, exist_ok=True)

    if not os.path.exists(source_dir):
        print("Source folder not found.")
        return

    for subdir in [
        d for d in os.listdir(source_dir)
        if os.path.isdir(os.path.join(source_dir, d))
        and not d.endswith("_results_dd")
    ]:
        print(f"\nStarting to process folder: {subdir}")
        process_category_folder(os.path.join(source_dir, subdir), result_dir)
    print("\nAll categories NeoSCA metric calculations completed.")


if __name__ == "__main__":
    main()