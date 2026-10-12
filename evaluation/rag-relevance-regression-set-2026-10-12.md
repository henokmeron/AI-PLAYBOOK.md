# RAG Relevance Evaluation — Fixed Regression Set (2026-10-12)

## Purpose

Keep retrieval changes evidence-driven. This is a small, explicitly labelled regression set for the two fictional demo documents, not a production-quality benchmark.

## Ground truth for the travel policy

The expenses policy says employees should book rail travel in standard class, book in advance where reasonably possible, and obtain manager approval before booking first-class rail travel. It does not specify train platforms, a required rail operator, a maximum ticket price, or whether sleeper trains are permitted.

## Fixed cases

| ID | Question | Label | Required behaviour |
|---|---|---|---|
| T1 | What class should employees book for rail travel? | Answerable | Answer standard class; cite expenses policy |
| T2 | What type of train ticket should employees choose? | Answerable paraphrase | Answer standard class; cite expenses policy |
| T3 | Which class of train journey is permitted by the policy? | Answerable paraphrase | Answer standard class; cite expenses policy |
| T4 | Which platform does the company train leave from? | Unanswerable | Abstain; no unsupported platform claim |
| T5 | Which rail operator must employees use? | Unanswerable | Abstain; no unsupported operator claim |
| T6 | What is the maximum permitted train ticket price? | Unanswerable | Abstain; no unsupported price claim |
| T7 | Can employees book a sleeper train? | Unanswerable | Abstain; policy does not establish this |
| T8 | What colour is the CEO's private yacht? | Unanswerable, unrelated | Abstain |
| T9 | What is the company's VAT registration number? | Unanswerable, unrelated | Abstain |
| T10 | How many business days do employees have to submit expense receipts? | Answerable control | Answer 10 business days; cite expenses policy |
| T11 | What hours is the support office staffed Monday to Friday? | Answerable control | Answer 09:00–17:30; cite employee handbook |
| T12 | Who must approve a single expense above £100? | Answerable control | Answer manager approval; cite expenses policy |

## Current observed results

- Existing six-case live regression: 5/6 passed. T2-style train-ticket paraphrase was abstained by the live service.
- Raw BM25 score for “What type of train ticket should employees choose?”: 0.728, ranking employee-handbook.md first.
- Original wording “What class should employees book for rail travel?”: 4.615, ranking expenses-policy.md first.
- “Which class of train journey is permitted by the policy?”: 3.156, ranking expenses-policy.md first.
- Naive global query expansion with “rail travel standard class book” raised the paraphrase to 5.280 but also raised the yacht, VAT, Paris office, platform, operator, ticket-price, and sleeper-train negatives above the provisional 2.30 threshold.
- Targeted expansion of the train-ticket paraphrase with “rail class standard” raised it to 3.190. This was only one positive and one unrelated negative control, so it is not a safe fix.
- No query expansion or threshold change has been deployed to the live gateway.

## Acceptance gates before deployment

1. All answerable cases return the expected fact and cite the correct file.
2. All unanswerable cases abstain without inventing facts; source retrieval alone is not treated as proof of answerability.
3. Existing six-case live smoke/regression stays green.
4. Compare current BM25 to a candidate second-stage evidence check on this same fixed set; do not tune the test set after seeing each result.
5. Add more paraphrases and hard negatives before making claims about general business-corpus quality.
6. Run tests in a temporary checkout and never change the live gateway until results are recorded and reviewed.

## Important interpretation

BM25 retrieval score measures lexical overlap, not whether a passage entails an answer. A high score from an expenses policy does not establish that the policy contains a train platform, operator, price cap, or sleeper-train rule. Avoid blanket synonym expansion and global threshold reductions.
