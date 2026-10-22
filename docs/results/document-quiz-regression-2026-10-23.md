# Synthetic document-quiz regression — 2026-10-23

Offline measurement of the quiz behaviour that the handbook run exposed. This corpus is nine generated text files. It is not the handbook PDF, and no model was called. These counts are not a live answer-quality score.

The old question box stored a 2,000-character prefix. The spreadsheet evidence ratio is 2.4 characters per token. Handbook prose now uses 4.4. The harness runs both ratios through `fit_history_to_budget` and `build_evidence` on the same retrieval.

| Check | Before | After |
| --- | --- | --- |
| Question stored | 2,000 characters, closing marker absent | 2,061 characters, closing marker present. The current limit is 8,000 and a longer paste is refused instead of cut. |
| Evidence ratio | 2.4 | 4.4 |
| Evidence budget | 6,558 characters | 18,078 characters |
| Chunks packed | 6 | 17 |
| Chunks dropped | 12 | 1 |
| Closing section packed | no | yes |

Retrieval returned 18 chunks from 9 files. Ten numbered items. The item whose terms are not in the corpus abstained (`low_query_coverage`), was omitted from the model prompt, and produced one "not answered" note. The other nine items did not abstain. A reply with no source label was withheld. A quote copied from the chunk and labelled `[Source 1]` was kept. A quote that is not in the chunk was withheld.

Command: `python eval/rag/document_quiz_regression.py` (exit 0). `python -m unittest rag.tests.test_document_quiz_regression` was 3 tests, exit 0. `python -m ops.run_tests` on Python 3.11 was 47 modules, 0 failed, exit 0, about 141 seconds. `api.test_gateway_reliability` logged a Windows socket abort and still passed.
