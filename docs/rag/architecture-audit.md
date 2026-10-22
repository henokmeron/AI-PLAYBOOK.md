# RAG / Document Q&A architecture audit

Date: 2026-10-14. Baseline audited: commit `6ebab4d` (branch `feature/qwen-a100-start-hardening`).
Scope: `rag/`, the RAG and reliability parts of `api/local_gateway.py`, `web/` source display.
Measured numbers referenced here are in `docs/results/rag-benchmark-2026-10-14.md` and
`eval/rag/results/`.

## 1. Pipeline (after this change)

```
upload (POST /v1/rag/documents, base64 JSON, <= 10 MiB file, 14 MiB body)
  -> document_library.validate_*  (name, extension, size, folder confinement)
  -> find_duplicate_content (sha256 against the same collection)   -> duplicate_of
  -> parse the bytes from a temp file first (reject unparsable / empty-text uploads)
  -> write into <managed root>/<collection>/<file>
  -> verify_document_searchable  (parses the new file; neighbours parsed tolerantly)
  -> RAG_STORE.invalidate(collection)

ask (POST /v1/rag/ask)
  -> validate question / history / top_k / collection
  -> RAG_STORE.load(folder)          FileBackedBm25Store: cache keyed by (name, size, mtime_ns)
       -> read_document_segments     page / sheet / table-row segments with metadata
       -> chunk_segments             row/paragraph-preserving chunks, CSV header pairing,
                                     filename terms; unreadable files -> skipped_files
  -> retrieval_pipeline.search       BM25 (k1=1.5, b=0.75) + dedupe + min score
                                     + IDF-weighted query-coverage gate (abstain reasons)
  -> fit_history_to_budget           drop oldest history pairs to keep >= 3000 evidence chars
  -> build_evidence(char_budget)     neutralise label spoofing, flag instruction-like text,
                                     truncate/drop sources to fit the 8192-token window
  -> Qwen (vLLM, OpenAI-compatible)  temperature 0, RAG_MAX_TOKENS
  -> check_citations                 cited [Source N] must exist in the evidence pack
  -> response: answer, sources(+location, flags, duplicate_files), retrieval{...}, usage
```

The files on disk are the system of record. Every index is derived and rebuildable.

## 2. Findings in the baseline and their status

| # | Finding (baseline 6ebab4d) | Impact | Status |
|---|---|---|---|
| F1 | Every `/v1/rag/ask` re-parsed and re-indexed the whole collection (`load_chunks`). | ~1 s of CPU per question on the 11-doc benchmark set, and the cost grows linearly with the collection. | Fixed: `FileBackedBm25Store` caches per file by (name, size, mtime_ns) and collection; upload/delete invalidate. |
| F2 | `load_chunks` is strict: one unreadable file made the whole collection fail, and made a *good* upload fail verification. | One corrupt file stops a tenant from using Q&A. | Fixed: tolerant per-file loading for asks and verification; skipped names returned as `retrieval.skipped_files`. `load_chunks` stays strict for existing callers. |
| F3 | PDF pages were joined with the literal string `\\n\\n` (backslash-n), not newlines. | Page boundaries invisible, tokens glued across pages, no page citation. | Fixed: real page segments with `[Page N]` and `meta.page`. |
| F4 | CSV/XLSX rows were chunked as plain text, without the header next to values; chunks could split mid-row. | Column meaning lost (`Leeds` without `depot=`); weak table retrieval. | Fixed: `col=value` pairing, header kept with every chunk, rows kept whole. Ablation: removing it drops recall@3 0.968 -> 0.955. |
| F5 | Tokeniser kept `snake_case` identifiers as one token and had no plural folding. | Misses on `placement_fee` vs "placement fee", "vehicles" vs "vehicle". | Fixed: `index_terms` (underscore split + conservative S-stemmer) for indexing only; `tokenize` unchanged. Ablation MRR: 0.969 vs 0.932 / 0.941 without each. |
| F6 | No retrieval-level abstention for managed collections (`RAG_MANAGED_MIN_SCORE=0`). | Any question with one common word reached the LLM with irrelevant evidence; abstention relied entirely on the model. | Improved: IDF-weighted query-coverage gate `RAG_MIN_COVERAGE=0.15`; 25% of unanswerable questions now abstain before the LLM, with 0 false abstentions on the benchmark. The model remains the second line. |
| F7 | No context budget: `top_k=20` plus maximum history overflowed Qwen's 8192-token window and returned **502**. | Hard failure on legal inputs. | Fixed: char budget derived from measured chars/token (2.4, lower bound of measured 2.44-4.48), history trimmed first, then sources truncated/dropped; reported in `retrieval`. Limits probe: 0 5xx. |
| F8 | Retrieved text was pasted into the prompt verbatim; a document could contain `[Source 1]` / `</evidence>` style labels or "ignore previous instructions". | Prompt injection / citation spoofing. | Improved: label spoofing neutralised to `(quoted Source N)`, instruction-like text flagged with a WARNING header and `sources[].flags`, system prompt treats evidence as data. 0/4 injection successes before and after (Qwen already resisted these four); defence is now explicit, not model-dependent. |
| F9 | Duplicate content uploaded under another name was silently indexed twice. | Duplicate sources waste context, confuse citations. | Fixed: `duplicate_of` on upload; ranked duplicates collapsed into one source with `duplicate_files`. |
| F10 | Request logging printed the raw request line (including query strings with filenames) to stderr. | Document names leak into logs. | Fixed: one JSON line per request: method, route template, status, duration, error id, client, retrieval counts. No question, answer, document text, filename or key. Test asserts this. |
| F11 | No socket timeout on the `ThreadingHTTPServer` handler. | Slow-loris clients hold threads forever. | Fixed: `PLATFORM_SOCKET_TIMEOUT` (30 s). |
| F12 | Rate-limit dict grew with every peer address forever. | Slow memory leak. | Fixed: pruned at 1024 peers. |
| F13 | Unhandled exceptions in handlers produced a dropped connection or a stack trace on stderr; errors had no correlation id. | Hard to debug, possible leak. | Fixed: `_dispatch` wrapper -> JSON 500 with `error_id` (also `X-Error-Id`), on every error response; console passes it through and shows it. |
| F14 | `/health` mixed liveness and readiness (it calls the upstream). | Orchestrator restarts a healthy gateway when Qwen is slow. | `/livez` is process-only and `/readyz` is the model check. On 2026-10-22 `/health` also returns HTTP 503 `unknown` when no model id is reported, so an empty list is not `ok`. Mock only. Not deployed. |
| F15 | Upstream failures collapsed into one generic 502. | No way to tell timeout from refusal. | Fixed: `reason` = `upstream_timeout`, `upstream_unreachable`, `upstream_bad_response`, `upstream_http_<code>`. |
| F16 | `api/openapi.yaml` had a duplicate `/v1/rag/documents` key (invalid YAML mapping) and stale limits. | Contract doc incorrect. | Fixed: v0.4.0, validated with `yaml.safe_load`. |
| F17 | Overwrite (`overwrite=true`) writes in place on the FUSE Global Volume; not atomic. | A crash mid-write can leave a truncated file (it will then be listed in `skipped_files`, not crash asks). | Open: atomic rename on geesefs is not guaranteed; documented. |
| F18 | Upload verification still parses the whole collection to count chunks. | Upload latency grows with collection size. | Open (low): acceptable at current sizes, see growth limits below. |
| F19 | Single shared bearer key; collections are scoping, not isolation. | Any key holder can read any collection. | Open: needs per-user identity -- design decision / approval required. |

## 3. Store decision: keep file-backed BM25, behind an interface

### Options considered

| Option | What it would add |
|---|---|
| **A. Keep** file-backed in-process BM25 (chosen) | Nothing new; now cached and behind `CollectionStore`. |
| B. SQLite FTS5 index file | Persistent lexical index; stdlib `sqlite3`. |
| C. Embedded vector DB (Chroma / FAISS / LanceDB) | Dense retrieval; needs an embedding model. |
| D. Vector server (Qdrant / pgvector) | A separate service to run, back up and secure. |

### Evidence

- **Quality headroom.** On benchmark v1, BM25 with the fixes reaches recall@3 0.968, MRR 0.969,
  doc recall 1.0. The remaining misses are a multi-hop question (q019, "Leeds" never named) and two
  rank-2 hits caused by a superseded document version (q037). Neither is a lexical-vs-semantic
  gap that embeddings would fix; q019 needs query decomposition. There is no measured gain to
  justify a dense model today. Benchmark v2 must add paraphrase/synonym questions before dense
  retrieval can be evaluated honestly.
- **Durability.** Documents live on the RunPod Global Volume (geesefs/FUSE) and are already the
  system of record. A derived index needs no durability of its own: it rebuilds from files in
  ~0.3 s for the benchmark set. Options B-D would put a database with mmap/WAL/locking on FUSE
  storage, where file-locking and fsync semantics are weaker than on local disk (SQLite documents
  network-filesystem locking problems; Qdrant requires a POSIX block filesystem). Putting them on
  container disk instead makes them non-durable, which brings back the rebuild path anyway.
- **Filtering.** Isolation is by collection folder (path-confined) plus `allowed_sources`.
  Metadata filters (page, sheet, row range, kind) are plain Python over `Chunk.meta`. No store
  capability is missing.
- **Latency.** Measured on the benchmark collection: search p50 ~0.25 ms; cold index build
  ~313 ms (was 993 ms per *question* in the baseline). LLM generation is 2-10 s, so retrieval is
  < 0.1% of request time.
- **Growth.** `eval/rag/scale_probe.py` (synthetic 180-word chunks, single thread, Windows dev
  box, Python 3.11):

  | chunks | build | search p50 | search max | peak Python memory* |
  |---:|---:|---:|---:|---:|
  | 1,000 | 22 ms | 1.4 ms | 2.4 ms | 21 MB |
  | 10,000 | 1.19 s | 17 ms | 51 ms | 206 MB |
  | 50,000 | 5.8 s | 121 ms | 341 ms | 1,028 MB |

  \*includes the generated chunk objects. BM25 here is a linear scan, so search time is
  proportional to chunks in *one collection* (collections are indexed separately; the store
  keeps at most 64 collections in memory). A maximum-size 10 MiB plain-text document yields roughly
  9-10k chunks at <= 1,200 chars per chunk, so a single collection stays comfortably interactive up to ~10k chunks.
- **Backup.** Only the document folders need backing up (already covered by the volume
  snapshot process owned by ops). No index format, schema migration or dump/restore.
- **Licence.** Current stack: Python stdlib, `pypdf` (BSD-3), `openpyxl` (MIT), `defusedxml`
  (PSF). Alternatives are also permissive (SQLite public domain, FAISS MIT, Chroma / Qdrant /
  LanceDB Apache-2.0, pgvector PostgreSQL licence), so licence is not a deciding factor;
  operational cost is.

### Decision

**Keep** the file-backed BM25 index. It is now behind `rag/retrieval_pipeline.py::CollectionStore`
(`load(folder) -> CollectionIndex`, `invalidate(folder=None)`), and the gateway only talks to
`RAG_STORE`. A replacement store only has to implement that protocol.

### Migration triggers (re-evaluate when any is true)

1. A single collection exceeds ~10,000 chunks, or retrieval p95 exceeds 100 ms in gateway logs
   -> option B (SQLite FTS5 on container disk, rebuilt from files at start; files stay the system of record).
2. Benchmark v2 shows a lexical gap (paraphrase/synonym recall@3 < 0.85) -> evaluate hybrid
   BM25 + small CPU embedding model (for example a ~130 MB bge-small class model under
   `/workspace/models-aux`). **Needs approval** (model download).
3. Multi-user access with per-user permissions is required -> isolation must be designed first
   (F19); a server store (D) only makes sense together with that.

## 4. Remaining risks

- Abstention for unanswerable questions still mostly relies on Qwen (gate catches 25%).
  Raising the gate to 0.20-0.25 catches more but produces false abstentions on answerable
  questions (`eval/rag/results/ablation-v1.json`).
- Version conflicts (2025 vs 2026 policy) are surfaced by the prompt ("report conflicts with
  filenames and dates"), not resolved by retrieval. No document-date metadata exists yet.
- chars/token is a fixed estimate; dense tables run at 2.44 chars/token. The budget uses 2.4,
  so it is conservative, but an unusual script/language could still overflow; the upstream
  error is then reported as `upstream_http_400` rather than crashing.
- The live start script (owned by ops) passes `PLATFORM_API_KEY` in the process environment,
  readable via `/proc/<pid>/environ` by root on the Pod.
