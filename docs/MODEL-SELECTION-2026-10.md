# Model Selection — October 2026

## Current decision

Do not immediately download the largest available model.

Mistral Large 4 was publicly previewed on 6 October 2026. Mistral describes it as a 1.05T-parameter, 49B-active-parameter, multimodal open-weight model with a 1M-token context window and strong coding, agentic and enterprise capabilities. Public weights are scheduled for later in October 2026.

Because the weights are not public yet, it is not currently our downloadable production base model.

## Prototype baseline

Google Gemma 4 is available as an open model family. Gemma 4 31B is available through Hugging Face and is listed with an Apache 2.0 licence.

We will use Gemma 4 as the first practical baseline only for building and testing the platform architecture. This is NOT a final claim that Gemma 4 is the best model.

## Important business rule

Model selection is separate from model ownership.

The business should be able to replace the underlying model without rewriting the platform.

## Next model evaluation

When Mistral Large 4 weights become available:

1. Verify the exact release and licence.
2. Download the weights to external storage, not GitHub.
3. Record the exact revision/hash in the registry.
4. Run our evaluation suite.
5. Compare against the current baseline.
6. Test inference cost, GPU requirements and latency.
7. Perform security/licence/compliance review.
8. Promote only if it passes our gates.

## Llama comparison

Meta Llama 4 remains a useful comparison candidate, but it uses a custom community licence rather than Apache 2.0. The exact licence obligations must be reviewed before commercial redistribution or derivative-model distribution.

## Lesson

We are building a model-independent AI platform, not tying the business to one model vendor.
