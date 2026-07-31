import os
import shutil
import tempfile

from leo_dd_python import calculate_folder_mdd_ndd


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    texts_folder = os.path.join(base_dir, "source", "text")
    temp_dir = tempfile.mkdtemp()

    try:
        metrics, _ = calculate_folder_mdd_ndd(texts_folder, "C:/", temp_dir)
        for filename, values in sorted(metrics.items()):
            print(f"{filename}: MDD_Leo={values['MDD_Leo']:.4f}, NDD_Leo={values['NDD_Leo']:.4f}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()