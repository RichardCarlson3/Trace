"""Offline inspection of the two cached Milestone 5 documents; no automatic fallback.

Run from the repository root after the explicit research downloads:
uv run --project apps/api python apps/api/scripts/inspect_tei_feasibility.py
"""

import hashlib
import json
import re
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from app.core.config import API_ROOT
from app.services.citation_identifiers import normalize_identifier, work_identifiers
from app.services.inference import InferenceService

ROOT = API_ROOT.parents[1]
CACHE = ROOT / ".cache/m5"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def local(element):
    return element.tag.rsplit("}", 1)[-1].lower()


def url_identity(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or parsed.query or parsed.fragment:
        return None
    return parsed.netloc.lower(), parsed.path.rstrip("/")


def bibliography_identifiers(bib):
    result = set()
    for node in bib.iter():
        if local(node) == "idno":
            kind = node.get("type", "").upper()
            if kind in ("DOI", "ARXIV", "PMID", "PMCID", "MAG"):
                try:
                    result.add((kind, normalize_identifier(kind, "".join(node.itertext()))))
                except ValueError:
                    pass
        if local(node) in ("ptr", "ref") and node.get("target", "").startswith("http"):
            identity = url_identity(node.get("target"))
            if identity:
                result.add(("URL", identity))
    return result


def inspect():
    baseline = json.loads((ROOT / "docs/reports/live_citation_verification.json").read_text())
    selected = [
        r
        for r in baseline["followup_run"]["relationships"]
        if r["status"] == "no_context" or r["citing_paper_id"] == "W2982399380"
    ]
    targets = {
        w["id"].rsplit("/", 1)[-1]: w
        for w in json.loads((CACHE / "targets.json").read_text())["results"]
    }
    downloads = json.loads((CACHE / "downloads.json").read_text())
    model = InferenceService(API_ROOT / "artifacts")
    report = {"downloads": downloads, "documents": [], "relationships": []}
    started = time.perf_counter()
    for document in downloads["documents"]:
        wid = document["id"]
        data = (CACHE / f"{wid}.xml").read_bytes()
        assert len(data) <= 10_000_000
        assert b"<!DOCTYPE" not in data and b"<!ENTITY" not in data
        assert hashlib.sha256(data).hexdigest() == document["sha256"]
        root = ET.fromstring(data)
        parent = {child: node for node in root.iter() for child in node}
        source = json.loads((CACHE / f"{wid}.metadata.json").read_text())
        assert source["id"] == f"https://openalex.org/{wid}"
        _, aliases = work_identifiers(source)
        header = next(n for n in root.iter() if local(n) == "teiheader")
        header_dois = [
            normalize_identifier("DOI", n.text)
            for n in header.iter()
            if local(n) == "idno" and n.get("type", "").upper() == "DOI"
        ]
        assert all(doi in aliases for doi in header_dois)
        bibs = [n for n in root.iter() if local(n) == "biblstruct" and n.get(XML_ID)]
        report["documents"].append(
            {
                **document,
                "title": source["title"],
                "license": (source.get("best_oa_location") or {}).get("license"),
                "source_identity": "header_doi_and_provider_work_path"
                if header_dois
                else "provider_work_path_only_no_header_identifier",
                "header_dois": header_dois,
                "bibliography_entries": len(bibs),
                "bibliography_entries_with_idno": sum(
                    any(local(n) == "idno" for n in b.iter()) for b in bibs
                ),
            }
        )
        for prior in selected:
            if prior["citing_paper_id"] != wid:
                continue
            cited = prior["cited_paper_id"]
            target = targets[cited]
            identifiers, _ = work_identifiers(target)
            known = set(identifiers.items())
            for location in target.get("locations", []):
                for field in ("landing_page_url", "pdf_url"):
                    if location.get(field):
                        identity = url_identity(location[field])
                        if identity:
                            known.add(("URL", identity))
            matches = [b for b in bibs if known & bibliography_identifiers(b)]
            row = {
                "citing_paper_id": wid,
                "cited_paper_id": cited,
                "target_doi": target.get("doi"),
                "bibliography_match_count": len(matches),
                "contexts": [],
            }
            report["relationships"].append(row)
            if len(matches) != 1:
                row["reason"] = (
                    "no_exact_bibliography_identifier" if not matches else "ambiguous_bibliography"
                )
                continue
            bib = matches[0]
            bid = bib.get(XML_ID)
            row.update(
                bibliography_id=bid,
                bibliography_xml=ET.tostring(bib, encoding="unicode"),
                identity_evidence=sorted(map(str, known & bibliography_identifiers(bib))),
            )
            seen = set()
            for marker in root.iter():
                if (
                    local(marker) != "ref"
                    or marker.get("type") != "bibr"
                    or f"#{bid}" not in marker.get("target", "").split()
                ):
                    continue
                ancestors = []
                node = marker
                while node in parent:
                    node = parent[node]
                    ancestors.append(node)
                if not any(local(a) == "body" for a in ancestors) or any(
                    local(a) in ("abstract", "listbibl", "figure", "table") for a in ancestors
                ):
                    continue
                sentence = next((a for a in ancestors if local(a) == "s"), None)
                if sentence is None:
                    continue
                text = "".join(sentence.itertext()).strip()
                # Conservative pilot guard; manually audit every accepted sentence as well.
                if not re.search(r"[.!?][\"')]*$", text) or text in seen:
                    continue
                seen.add(text)
                section = next((a for a in ancestors if local(a) == "div"), None)
                headings = (
                    ["".join(n.itertext()) for n in section if local(n) == "head"]
                    if section is not None
                    else []
                )
                row["contexts"].append(
                    {
                        "context_text": text,
                        "section": headings,
                        "marker_xml": ET.tostring(marker, encoding="unicode"),
                        "sentence_xml": ET.tostring(sentence, encoding="unicode"),
                        "source_url": document["source_url"],
                        "document_sha256": document["sha256"],
                        "classification": model.classify(text).model_dump(),
                    }
                )
            row["reason"] = None if row["contexts"] else "no_verified_body_sentence"
    report["offline_parse_and_inference_seconds"] = time.perf_counter() - started
    (CACHE / "extraction.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "documents": len(report["documents"]),
                "matched_relationships": sum(
                    r["bibliography_match_count"] == 1 for r in report["relationships"]
                ),
                "recovered_relationships": sum(
                    bool(r["contexts"]) for r in report["relationships"]
                ),
                "sentences": sum(len(r["contexts"]) for r in report["relationships"]),
                "offline_seconds": report["offline_parse_and_inference_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    inspect()
