import os
import re
import csv
import math
import shutil
import pandas as pd
from collections import deque
import stanza
from quansyn.depval import DepValAnalyzer
from leo_dd_python import calculate_folder_mdd_ndd


def text_to_conllu(text: str, nlp) -> str:
    try:
        doc = nlp(text)
    except Exception as e:
        print(f"Failed: {e}")
        return ""
    conllu_lines = []
    for sent in doc.sentences:
        for word in sent.words:
            line = (
                f"{word.id}\t{word.text}\t{word.lemma}\t{word.upos}\t"
                f"{word.xpos if word.xpos else '_'}\t"
                f"{word.feats if word.feats else '_'}\t"
                f"{word.head}\t{word.deprel}\t_\t_"
            )
            conllu_lines.append(line)
        conllu_lines.append("")
    print("Conversion completed.")
    return "\n".join(conllu_lines)


def parse_conllu(conllu_str: str):
    sentences = []
    current_sent = []
    for line in conllu_str.strip().split("\n"):
        line = line.strip()
        if not line:
            if current_sent:
                sentences.append(current_sent)
                current_sent = []
        elif not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) == 10 and parts[0].isdigit() and parts[6].isdigit():
                current_sent.append(parts)
    if current_sent:
        sentences.append(current_sent)
    return sentences


def get_valid_node_info(sent_tokens):
    n_total = len(sent_tokens)
    if n_total <= 1:
        return 0, [], []

    id_to_idx = {int(t[0]): i for i, t in enumerate(sent_tokens)}
    root_idx = next((i for i, t in enumerate(sent_tokens) if int(t[6]) == 0), None)
    if root_idx is None:
        return 0, [], []

    children = [[] for _ in range(n_total)]
    for i, t in enumerate(sent_tokens):
        head = int(t[6])
        if head != 0 and head in id_to_idx:
            children[id_to_idx[head]].append(i)

    depths = [-1] * n_total
    depths[root_idx] = 0
    q = deque([root_idx])
    while q:
        cur = q.popleft()
        for child in children[cur]:
            if depths[child] == -1:
                depths[child] = depths[cur] + 1
                q.append(child)

    valid_indices = [
        i for i, t in enumerate(sent_tokens)
        if t[3] not in ("PUNCT", "SYM", "X") and depths[i] != -1
    ]
    valid_depths = [depths[i] for i in valid_indices]
    return len(valid_indices), valid_depths


def compute_alpha_deplength(n_valid, valid_depths):
    if n_valid <= 1:
        return 0.0
    sum_depth = sum(d for d in valid_depths if d > 0)
    mhl = sum_depth / (n_valid - 1)
    return (n_valid - 1) / mhl if mhl > 0 else 0.0


def compute_mhdd(n_valid, valid_depths):
    if n_valid <= 1:
        return 0.0
    maxhl = max(valid_depths) + 1 if valid_depths else 0
    return (n_valid - 1) / maxhl if maxhl > 0 else 0.0


def compute_mdd(sent_tokens):
    valid_tokens = [t for t in sent_tokens if t[3] not in ("PUNCT", "SYM", "X")]
    total_dist = 0
    n_rel = 0
    for t in valid_tokens:
        head = int(t[6])
        if head == 0:
            continue
        idx = int(t[0])
        total_dist += abs(idx - head)
        n_rel += 1
    if n_rel == 0:
        return 0.0
    return total_dist / n_rel


def compute_ndd(mdd, root_distance, sentence_length):
    if mdd <= 0 or root_distance <= 0 or sentence_length <= 0:
        return 0.0
    denominator = math.sqrt(root_distance * sentence_length)
    if denominator == 0:
        return 0.0
    return abs(math.log(mdd / denominator))


def compute_metrics(conllu_str: str):
    sentences = parse_conllu(conllu_str)
    alpha_list, mhdd_list, mdd_list, ndd_list = [], [], [], []

    for sent in sentences:
        valid_tokens = [t for t in sent if t[3] not in ("PUNCT", "SYM", "X")]
        if len(valid_tokens) <= 1:
            continue

        root_tokens = [t for t in valid_tokens if int(t[6]) == 0]
        if not root_tokens:
            continue
        root_distance = int(root_tokens[0][0])
        n_valid, valid_depths = get_valid_node_info(sent)
        n_rel = sum(1 for t in valid_tokens if int(t[6]) != 0)
        sentence_length = n_rel

        alpha = compute_alpha_deplength(n_valid, valid_depths)
        mhdd = compute_mhdd(n_valid, valid_depths)
        mdd = compute_mdd(sent)
        ndd = compute_ndd(mdd, root_distance, sentence_length)

        if alpha > 0:
            alpha_list.append(alpha)
        if mhdd > 0:
            mhdd_list.append(mhdd)
        if mdd > 0:
            mdd_list.append(mdd)
        if ndd > 0:
            ndd_list.append(ndd)

    avg = lambda x: sum(x) / len(x) if x else 0.0
    print("Parsing completed.")
    return {
        "MHDD": round(avg(mhdd_list), 4),
        "AlphaDepLength": round(avg(alpha_list), 4),
        "MDD": round(avg(mdd_list), 4),
        "NDD": round(avg(ndd_list), 4),
    }


def compute_quansyn_text_metrics(conllu_str: str):
    metrics_needed = ["mhd", "tdl", "sl", "mv", "vk", "hi", "hf", "mtw", "mth", "mtdl", "msl", "mdd", "ndd"]
    try:
        analyzer = DepValAnalyzer(conllu_str)
        text_metrics = analyzer.calculate_text_metrics(metrics=metrics_needed)
    except Exception as e:
        print(f"Error: {e}")
        return {}

    rename_map = {
        "mhd": "MHD", "tdl": "TDL", "sl": "SL", "mv": "MV", "vk": "VK",
        "hi": "HI", "hf": "HF", "mtdl": "MTDL", "msl": "MSL",
        "mtw": "MTW", "mth": "MTH", "mdd": "MDD_quansyn", "ndd": "NDD_quansyn"
    }
    result = {}
    for raw_key, friendly_key in rename_map.items():
        if raw_key in text_metrics:
            val = text_metrics[raw_key]
            if isinstance(val, (int, float)):
                result[friendly_key] = round(float(val), 4)
            else:
                result[friendly_key] = val
    print("Parsing completed.")
    return result


def compute_leo_metrics(folder_path: str, source_path: str, category_name: str):
    results_dir = os.path.join(source_path, f"{category_name}_results_dd")

    try:
        leo_map, results_dir = calculate_folder_mdd_ndd(
            texts_folder=folder_path,
            language_model_folder="C:/",
            results_folder=results_dir,
        )
    except Exception as e:
        print(f"Leo Python calculation failed: {e}")
        return {}, results_dir
    print("Parsing completed.")
    return leo_map, results_dir


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


ALL_OUTPUT_FIELDS = [
    "filename",
    "MHDD", "AlphaDepLength", "MDD", "NDD",
    "MDD_Leo", "NDD_Leo",
    "MDD_quansyn", "NDD_quansyn",
    "MHD", "MV", "VK", "MTW", "MTH", "HI", "HF", "MTDL", "MSL"
]


def process_category_folder(category_path: str, output_dir: str, nlp, source_dir):
    category_name = os.path.basename(category_path)
    output_csv = os.path.join(output_dir, f"{category_name}.csv")

    if not os.path.exists(category_path):
        print(f"Folder path {category_path} does not exist, skipping to the next folder.")
        return
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
            print(f"Existing progress file found, {len(processed_files)} files already processed.")
        except Exception as e:
            print(f"Error reading progress file, restarting: {e}")
            processed_files = set()
            existing_fieldnames = None

    txt_files = [f for f in txt_files_all if f not in processed_files]
    if not txt_files:
        print("All files have been processed, nothing to continue.")
        return

    leo_results_dir = os.path.join(source_dir, f"{category_name}_results_dd")
    #leo_results_dir = os.path.join(leo_dir, "text_results_dd")
    leo_csv_path = os.path.join(leo_results_dir, "0mdd_ndd_results.csv")
    leo_metrics = {}

    if os.path.exists(leo_csv_path):
        try:
            df = pd.read_csv(leo_csv_path)
            for _, row in df.iterrows():
                fname = f"{row['file_id']}.txt"
                leo_metrics[fname] = {
                    "MDD_Leo": round(float(row['mdd']), 4),
                    "NDD_Leo": round(float(row['ndd']), 4)
                }
            print(f"Loaded Leo metrics from existing file, total {len(leo_metrics)} files.")
        except Exception as e:
            print(f"Failed to read existing Leo results ({e}), will recalculate.")
            shutil.rmtree(leo_results_dir, ignore_errors=True)
            leo_metrics, leo_results_dir = compute_leo_metrics(category_path, source_dir, category_name)
    else:
        print("No Leo results found, starting calculation...")
        leo_metrics, leo_results_dir = compute_leo_metrics(category_path, source_dir, category_name)

    if existing_fieldnames is None:
        fieldnames = ALL_OUTPUT_FIELDS
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
            print("Starting to read txt file...")
            file_path = os.path.join(category_path, txt_file)
            text_content = clean_text(extract_text_from_file(file_path))
            if not text_content:
                print(f"{txt_file}: text is empty, skipping")
                continue
            print(f"{txt_file}: {text_content[:30]}...")
            print("Converting to CoNLL-U...\t", end=" ")
            conllu_str = text_to_conllu(text_content, nlp)

            print("Calculating metrics...\t", end=" ")
            computed_metrics = compute_metrics(conllu_str)

            print("Calculating QuanSyn metrics...\t", end=" ")
            qs_metrics = compute_quansyn_text_metrics(conllu_str)

            row = {"filename": txt_file}
            row.update(computed_metrics)
            if txt_file in leo_metrics:
                row.update(leo_metrics[txt_file])
            row.update(qs_metrics)

            filtered_row = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(filtered_row)
            csvfile.flush()
            print(f"  Write completed: {txt_file}")

    final_processed = set()
    if os.path.exists(output_csv):
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                final_processed.add(row["filename"])
    if len(final_processed) == len(txt_files_all):
        # Uncomment if cleanup is desired
        shutil.rmtree(leo_results_dir, ignore_errors=True)  
        print(f"All files completed, Leo temporary folder {leo_results_dir} has been deleted.")
    else:
        print(f"{len(txt_files_all) - len(final_processed)} files remaining unprocessed, keeping Leo results for resuming.")

    print(f"Folder {category_name} processing completed, results saved to {output_csv}")


def main():
    print("\nConnecting to Stanza ...")
    nlp = stanza.Pipeline('en', processors='tokenize,pos,lemma,depparse', verbose=False, use_gpu=False)
    print("Stanza connected successfully.")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    source_dir = os.path.join(base_dir, "source")
    result_dir = os.path.join(base_dir, "result")
    os.makedirs(result_dir, exist_ok=True)

    if not os.path.exists(source_dir):
        print("Source folder not found.")
        return

    for subdir in [
        d
        for d in os.listdir(source_dir)
        if os.path.isdir(os.path.join(source_dir, d))
        and not d.endswith("_results_dd")
    ]:
        print(f"\nStarting to process category: {subdir}")
        process_category_folder(os.path.join(source_dir, subdir), result_dir, nlp, source_dir)

    print("\nAll categories processed.")


if __name__ == "__main__":
    main()