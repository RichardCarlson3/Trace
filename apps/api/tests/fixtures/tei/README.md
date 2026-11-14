# Recorded TEI fixtures

`bart.xml` and `biobert.xml` are the unchanged OpenAlex GROBID XML downloaded in
Milestone 5 on 2026-11-14. Their hashes, authenticated source URLs and attribution
are recorded in `docs/reports/tei_feasibility.json`. OpenAlex metadata reported CC BY.
BART: Mike Lewis et al., https://aclanthology.org/2020.acl-main.703/.
BioBERT: Jinhyuk Lee et al., https://doi.org/10.1093/bioinformatics/btz682.

`works.json` records the corresponding OpenAlex metadata and eleven target records.
The two citing works' `referenced_works` fields are restricted to selected outgoing
edges independently verified in the historical 28-pair report; they are not full
reference lists. Tests block external HTTP. Tests that mutate these records/XML use
explicit synthetic failure/enrichment variants and are not live recovery evidence.
