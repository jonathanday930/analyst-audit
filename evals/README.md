# Evals (DeepEval)

Our own eval framework for the claim pipeline, built on DeepEval with a judge backed by the app's
Anthropic client. It runs from its own venv, `evals/.venv`, so DeepEval stays out of the backend's
dependencies. Keys come from `backend/.env`. Nothing is sent to DeepEval's hosted dashboard.

## What gets evaluated

For one transcript that yields, say, 5 claims, every claim is handled on its own:

1. **Claim accuracy** (layer 1). Is this one claim faithful to the transcript? Six yes/no judge
   checks: falsifiable, the analyst's own view, wording matches the transcript, grounds supported,
   implication faithful, conditions faithful.
2. **Claim analyzer runs** on each claim (done by `generate.py`, using the same price, benchmark and
   web-search inputs as the real pipeline). This is the "test whether the claim was correct" step.
3. **Analyzer output** (layer 3). Is that analyzer result sound? One code check (fields are
   internally consistent, no premature resolution, benchmark arithmetic) plus four judge checks
   (verdict supported by the price evidence, cited numbers match the data, rationale agrees with the
   verdict, judged the claim as stated).

Code is in `metrics.py`; the judge is `judge_model.py`; renderings of claims for the judge are in
`formatting.py`.

## Running

Generation (LLM and price calls, costs money) is separate from scoring, so you can tweak metrics
without regenerating. Always from the repo root or anywhere; paths are absolute.

```bash
evals/.venv/bin/python evals/generate.py                 # frozen claims -> analyzer on each claim
evals/.venv/bin/python evals/generate.py --fresh         # re-run the claim finder too
evals/.venv/bin/python evals/generate.py --video ID --force   # redo one video's analyzer results
cd evals && .venv/bin/deepeval test run tests/           # score everything
cd evals && .venv/bin/python -m pytest tests/ -k Cowen   # plain pytest, one channel
```

Cases are cached in `evals/cache/cases/<video_id>.json` (gitignored; includes transcripts).
The analyzer's answer depends on today's date and the news, so each case records its `as_of` date.

## Notes

- The judge model defaults to `claude-sonnet-5`; override with `EVAL_JUDGE_MODEL`. When testing a
  swapped-in model for a pass, keep the judge pinned to Claude so it doesn't grade itself.
- Claude judging Claude agrees with itself too readily. Treat layer 1 and 3 scores as a screen
  until they are calibrated against human labels (see `TASKS.md`).
- The judge for the analyzer sees only price evidence, not web-search findings, so claims decided by
  news can't have their facts verified, only their internal logic.
- Run generation one process at a time: YouTube and yfinance rate limits (see `../testing/README.md`).
