# Baseline Model Evaluation

This folder begins Phase 2 of the LLM Build Playbook. The first suite is deliberately small and has no third-party Python dependencies.

## What it checks

1. Exact instruction following.
2. A simple arithmetic answer.
3. Faithful use of information supplied in the prompt.
4. Valid JSON structured output.

These are smoke/baseline checks only. Passing them does not establish general reasoning ability, business accuracy, security, or regulatory compliance. Expand the suite as use cases and customer needs become clear.

## Run against the current vLLM server

Keep the vLLM server running in its existing terminal. In a second terminal on the same Pod, download and run the script:

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/evaluation/run_chat_eval.py -o /tmp/run_chat_eval.py
python /tmp/run_chat_eval.py
```

The default API is `http://127.0.0.1:8000/v1`; the script discovers the model ID from `/v1/models`. To test a different OpenAI-compatible endpoint, set `VLLM_BASE_URL`; to override model selection, set `VLLM_MODEL_ID`.

Example:

```bash
VLLM_BASE_URL=http://127.0.0.1:8000/v1 python /tmp/run_chat_eval.py
```

A non-zero exit code means at least one check failed or the API could not be reached. Review the individual output. Do not change or reinstall the model to make a test pass; first determine whether the failure is in the server, prompt, or test expectation.

## Baseline recording

Do not mark Gemma as approved/production based on these four checks. Record the date, runtime profile, outputs, pass rate, and known limitations. Run the same tests against each candidate model with the same prompts and comparable settings.
