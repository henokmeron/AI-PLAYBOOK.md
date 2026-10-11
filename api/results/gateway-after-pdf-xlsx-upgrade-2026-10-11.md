# Gateway after PDF + XLSX dependency upgrade — 2026-10-11

## Result

**PASS: ALL GATEWAY + RAG API TESTS PASSED** in the user's RunPod terminal screenshot after the guarded upgrade.

## Confirmed dependencies

The script printed:
- pypdf 6.20.0
- openpyxl 3.1.5
- et-xmlfile 2.0.0
- defusedxml 0.7.1

## Confirmed gateway checks

- New gateway and shared RAG engine passed Python syntax compilation.
- The old gateway process (PID 3118) was stopped and the updated loopback gateway was started; the script explicitly stated that vLLM was not touched.
- Health returned `{"status":"ok","upstream":"ok","model_count":1}`.
- Unauthenticated RAG request was rejected.
- Authenticated expense-policy question returned the supported 10-business-day answer and source metadata.
- The low-relevance yacht-colour question abstained, with top score 0.69 below demo threshold 2.3, before generation.
- Final output: `ALL GATEWAY + RAG API TESTS PASSED.`
- Main gateway remains at `http://127.0.0.1:8010`; temporary shared key remains at `/tmp/platform-gateway.key`.

## Scope

This confirms the main gateway starts with the pinned PDF/XLSX parser dependencies available and the Markdown demo cases still pass. It does **not yet** verify the four formats end-to-end. Next run `api/test_format_ingestion.sh`, which tests CSV, DOCX, searchable PDF and XLSX through an isolated temporary gateway on port 8011. The live main gateway and vLLM should remain untouched.
