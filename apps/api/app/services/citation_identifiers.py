"""Exact work identifiers from provider metadata; no title or URL guessing."""

import re
from urllib.parse import unquote, urlsplit


def normalize_doi(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("DOI must be a string")
    value = value.strip()
    if value.lower().startswith("doi:"):
        value = value[4:].strip()
    if value.lower().startswith(("https://", "http://")):
        url = urlsplit(value)
        if url.netloc.lower() not in ("doi.org", "dx.doi.org"):
            raise ValueError("Expected a DOI resolver URL")
        if re.search(r"%(?![0-9a-fA-F]{2})", url.path):
            raise ValueError("Invalid DOI encoding")
        value = unquote(url.path.removeprefix("/"), errors="strict")
    if not re.fullmatch(r"10\.[0-9]+(?:\.[0-9]+)*/\S+", value) or any(
        ord(c) < 32 or ord(c) == 127 for c in value
    ):
        raise ValueError("Invalid DOI")
    return value.translate(
        str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    )


def normalize_identifier(kind: str, value: str) -> str:
    if kind == "DOI":
        return normalize_doi(value)
    if not isinstance(value, str):
        raise ValueError("Expected an identifier string")
    value = value.strip()
    if value.startswith(("http://", "https://")):
        url = urlsplit(value)
        hosts = {
            "ARXIV": {"arxiv.org", "www.arxiv.org", "export.arxiv.org"},
            "PMID": {"pubmed.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"},
            "PMCID": {"pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"},
        }
        if url.netloc.lower() not in hosts.get(kind, set()) or url.query or url.fragment:
            raise ValueError("Unexpected identifier URL")
        value = url.path.strip("/")
        prefixes = {
            "ARXIV": ("abs/", "pdf/"),
            "PMID": ("pubmed/",),
            "PMCID": ("pmc/articles/", "articles/"),
        }
        for prefix in prefixes.get(kind, ()):
            if value.startswith(prefix):
                value = value[len(prefix) :]
                break
        if kind == "ARXIV" and value.endswith(".pdf"):
            value = value[:-4]
    value = re.sub(rf"^{kind}:", "", value, flags=re.IGNORECASE)
    if kind == "ARXIV":
        value = re.sub(r"v[1-9][0-9]*$", "", value)
        if re.fullmatch(r"(?:[0-9]{4}\.[0-9]{4,5}|[a-zA-Z-]+(?:\.[A-Z]{2})?/[0-9]{7})", value):
            return value
    elif kind == "PMCID":
        value = re.sub(r"^PMC", "", value, flags=re.IGNORECASE)
        if re.fullmatch(r"[1-9][0-9]*", value):
            return value
    elif kind in ("PMID", "MAG") and re.fullmatch(r"[1-9][0-9]*", value):
        return value
    raise ValueError("Invalid paper identifier")


EXTERNAL_FIELDS = {
    "DOI": "DOI",
    "ARXIV": "ArXiv",
    "PMID": "PubMed",
    "PMCID": "PubMedCentral",
    "MAG": "MAG",
}


def work_identifiers(work: dict) -> tuple[dict[str, str], set[str]]:
    """At most one identifier per namespace; conflicting alternatives fail closed."""
    values: dict[str, set[str]] = {k: set() for k in EXTERNAL_FIELDS}
    aliases = set()
    ids = work.get("ids") or {}
    locations = work.get("locations") or []
    if not isinstance(locations, list):
        raise ValueError("invalid_openalex_locations")
    for kind in values:
        raw = [ids.get(kind.lower())]
        if kind == "DOI":
            raw.append(work.get("doi"))
        if kind == "ARXIV":
            for location in locations:
                if not isinstance(location, dict):
                    continue
                lid = location.get("id", "")
                if isinstance(lid, str) and lid.startswith("pmh:oai:arXiv.org:"):
                    raw.append(lid[len("pmh:oai:arXiv.org:") :])
                for field in ("landing_page_url", "pdf_url"):
                    url = location.get(field)
                    if isinstance(url, str):
                        try:
                            if urlsplit(url).hostname in (
                                "arxiv.org",
                                "www.arxiv.org",
                                "export.arxiv.org",
                            ):
                                raw.append(url)
                        except ValueError:
                            continue
        for value in raw:
            if value:
                try:
                    values[kind].add(normalize_identifier(kind, value))
                except ValueError:
                    continue
        if len(values[kind]) > 1:
            raise ValueError(f"ambiguous_{kind.lower()}_identifier")
    for location in locations:
        if isinstance(location, dict):
            lid = location.get("id")
            if isinstance(lid, str) and lid.startswith("doi:"):
                try:
                    aliases.add(normalize_doi(lid))
                except ValueError:
                    pass
    result = {k: next(iter(v)) for k, v in values.items() if v}
    aliases.update(values["DOI"])
    return result, aliases


def identity_matches(paper: dict, kind: str, value: str, known: dict, aliases: set) -> bool:
    external = paper.get("externalIds") or {}
    if not isinstance(external, dict):
        return False
    try:
        if normalize_identifier(kind, external.get(EXTERNAL_FIELDS[kind])) != value:
            return False
        for other, expected in known.items():
            returned = external.get(EXTERNAL_FIELDS[other])
            if returned:
                actual = normalize_identifier(other, returned)
                if other == "DOI":
                    if actual not in aliases:
                        return False
                elif actual != expected:
                    return False
    except ValueError:
        return False
    return True
