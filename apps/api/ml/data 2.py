"""Load the official SciCite files with the supported Hugging Face JSON reader."""

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

from app.core.config import API_ROOT, get_settings

LABEL_NAMES = ("method", "background", "result")
DATASET_REVISION = "4c40e64d8eebd9c0a8f27bb630cfbaeffc01c941"
ARCHIVE_URL = "https://s3-us-west-2.amazonaws.com/ai2-s2-research/scicite/scicite.tar.gz"
ARCHIVE_SHA256 = "711ece2c4e61d116c8ae5bb07e9fbb2ee9ff7bba004b4cab7fbd0ac3af499193"
SPLIT_FILES = {"train": "train.jsonl", "validation": "dev.jsonl", "test": "test.jsonl"}
DEFAULT_DATA_DIR = API_ROOT / "data" / "scicite"


@dataclass
class SciCiteData:
    splits: dict[str, list[dict]]
    report: dict


def file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def encode_label(value: str | int) -> int:
    if isinstance(value, str) and value in LABEL_NAMES:
        return LABEL_NAMES.index(value)
    if type(value) is int and 0 <= value < len(LABEL_NAMES):
        return value
    raise ValueError(f"Invalid SciCite label {value!r}")


def context_key(text: str) -> str:
    """Normalize only for overlap detection. Keep original model inputs intact."""
    return " ".join(text.split()).casefold()


def split_arrays(rows: list[dict]) -> tuple[list[str], list[str]]:
    contexts = [row["string"] for row in rows]
    if not contexts or any(not isinstance(text, str) or not text.strip() for text in contexts):
        raise ValueError(
            "Model inputs require a nonempty split of genuine, nonblank citation contexts"
        )
    return contexts, [LABEL_NAMES[row["label"]] for row in rows]


def download_scicite(data_dir: Path) -> None:
    from datasets import DownloadConfig, DownloadManager

    if all((data_dir / filename).is_file() for filename in SPLIT_FILES.values()):
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    manager = DownloadManager(
        download_config=DownloadConfig(cache_dir=str(data_dir / ".downloads"))
    )
    archive = Path(manager.download(ARCHIVE_URL))
    if file_sha256(archive) != ARCHIVE_SHA256:
        raise ValueError("SciCite archive checksum differs from the verified source")
    # Read only known files. Do not extract arbitrary archive paths or execute scripts.
    import tarfile

    with tarfile.open(archive) as source:
        for filename in SPLIT_FILES.values():
            member = source.extractfile(f"scicite/{filename}")
            if member is None:
                raise ValueError(f"Missing SciCite file {filename}")
            temporary = data_dir / f"{filename}.tmp"
            with member, temporary.open("wb") as destination:
                destination.write(member.read())
            temporary.replace(data_dir / filename)


def _project_file(path: Path, destination: Path) -> dict:
    """Keep model/evidence identifiers, avoiding inconsistent ancillary raw fields."""
    field_types = {}
    count = 0
    with path.open(encoding="utf-8") as source, destination.open("w", encoding="utf-8") as output:
        for line in source:
            row = json.loads(line)
            for key, value in row.items():
                field_types.setdefault(key, set()).add(type(value).__name__)
            text = row.get("string")
            if text is not None and not isinstance(text, str):
                raise ValueError("SciCite string field must contain text or null")
            unique_id = row.get("unique_id")
            if not isinstance(unique_id, str) or not unique_id:
                raise ValueError("SciCite rows require a nonempty unique_id")
            projected = {
                "string": text,
                "label": encode_label(row["label"]),
                "unique_id": unique_id,
                "citingPaperId": str(row.get("citingPaperId", "")),
                "citedPaperId": str(row.get("citedPaperId", "")),
            }
            output.write(json.dumps(projected, ensure_ascii=False) + "\n")
            count += 1
    return {
        "raw_rows": count,
        "raw_schema": {key: sorted(value) for key, value in field_types.items()},
    }


def split_statistics(rows: list[dict]) -> dict:
    contexts = [row["string"] for row in rows]
    usable = [text for text in contexts if isinstance(text, str) and text.strip()]
    counts = Counter(LABEL_NAMES[row["label"]] for row in rows)

    def summarize(values: list[int]) -> dict:
        if not values:
            return {"min": None, "max": None, "mean": None, "median": None}
        return {
            "min": min(values),
            "max": max(values),
            "mean": mean(values),
            "median": median(values),
        }

    return {
        "rows": len(rows),
        "class_counts": {label: counts[label] for label in LABEL_NAMES},
        "missing_contexts": sum(text is None for text in contexts),
        "empty_contexts": sum(isinstance(text, str) and not text.strip() for text in contexts),
        "characters": summarize([len(text) for text in usable]),
        "words": summarize([len(text.split()) for text in usable]),
    }


def _overlap(left: list[dict], right: list[dict]) -> dict:
    return {
        "shared_unique_ids": len(
            {row["unique_id"] for row in left} & {row["unique_id"] for row in right}
        ),
        "shared_contexts": len(
            {context_key(row["string"]) for row in left if row["string"]}
            & {context_key(row["string"]) for row in right if row["string"]}
        ),
    }


def prepare_splits(splits: dict[str, list[dict]]) -> tuple[dict[str, list[dict]], dict]:
    """Keep test intact and prevent held-out IDs/contexts entering model fitting."""
    cleaned = {"test": splits["test"]}
    excluded = {"test": 0}
    for name, held_out_names in (("validation", ("test",)), ("train", ("validation", "test"))):
        held_out = [row for split in held_out_names for row in splits[split]]
        ids = {row["unique_id"] for row in held_out}
        contexts = {context_key(row["string"]) for row in held_out if row["string"]}
        cleaned[name] = [
            row
            for row in splits[name]
            if row["unique_id"] not in ids and context_key(row["string"] or "") not in contexts
        ]
        excluded[name] = len(splits[name]) - len(cleaned[name])
    pairs = (("train", "validation"), ("train", "test"), ("validation", "test"))
    return cleaned, {
        "policy": (
            "Preserve test; exclude held-out unique_ids and whitespace/case-normalized "
            "contexts from earlier splits"
        ),
        "excluded_rows": excluded,
        "original_overlap": {f"{a}/{b}": _overlap(splits[a], splits[b]) for a, b in pairs},
        "effective_overlap": {f"{a}/{b}": _overlap(cleaned[a], cleaned[b]) for a, b in pairs},
    }


def load_scicite(data_dir: Path = DEFAULT_DATA_DIR) -> SciCiteData:
    from datasets import ClassLabel, DownloadConfig, Features, Value, load_dataset

    data_dir = data_dir.resolve()
    download_scicite(data_dir)
    prepared_dir = data_dir / "prepared"
    prepared_dir.mkdir(exist_ok=True)
    raw_info = {}
    projected_files = {}
    hashes = {}
    for name, filename in SPLIT_FILES.items():
        raw_path = data_dir / filename
        hashes[name] = file_sha256(raw_path)
        destination = prepared_dir / filename
        raw_info[name] = _project_file(raw_path, destination)
        projected_files[name] = str(destination)
    features = Features(
        {
            "string": Value("string"),
            "label": ClassLabel(names=list(LABEL_NAMES)),
            "unique_id": Value("string"),
            "citingPaperId": Value("string"),
            "citedPaperId": Value("string"),
        }
    )
    dataset = load_dataset(
        "json",
        data_files=projected_files,
        features=features,
        cache_dir=str(data_dir / ".hf_cache"),
        download_config=DownloadConfig(local_files_only=True),
    )
    splits = {}
    split_reports = {}
    for name in SPLIT_FILES:
        unique_rows = {}
        for row in dataset[name]:
            unique_rows.setdefault(row["unique_id"], row)
        splits[name] = list(unique_rows.values())
        split_reports[name] = {
            **raw_info[name],
            "duplicate_ids_removed": len(dataset[name]) - len(splits[name]),
            **split_statistics(splits[name]),
        }
    cleaned, audit = prepare_splits(splits)
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return SciCiteData(
        cleaned,
        {
            "dataset_id": "allenai/scicite",
            "reference_revision": DATASET_REVISION,
            "archive_url": ARCHIVE_URL,
            "expected_archive_sha256": ARCHIVE_SHA256,
            "file_sha256": hashes,
            "fingerprint": fingerprint,
            "label_mapping": dict(enumerate(LABEL_NAMES)),
            "features": dataset["train"].features.to_dict(),
            "official_splits": split_reports,
            "overlap_audit": audit,
            "effective_splits": {name: split_statistics(rows) for name, rows in cleaned.items()},
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--output", type=Path, default=get_settings().model_artifact_dir / "dataset_report.json"
    )
    args = parser.parse_args()
    data = load_scicite(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data.report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data.report, indent=2))


if __name__ == "__main__":
    main()
