# Prompt — Earnings Transcript Classifier (Chapter 5)

**Used by:** `strategies/earnings.py::classify_transcript` · **Model:** `claude-sonnet-4-6` · **max_tokens:** 200

## The prompt (book-verbatim)

```text
Read this earnings call transcript and classify the company's quarterly results.

Return a JSON object with EXACTLY these fields and no extra text:
{
  "headline_result": "beat" | "in_line" | "miss",
  "guidance_change": "raised" | "maintained" | "cut" | "withdrawn",
  "margin_direction": "expanding" | "flat" | "contracting",
  "sector_tone": "bullish" | "neutral" | "bearish",
  "confidence": <integer 1-10>
}

Rules:
- "headline_result" reflects EPS and revenue versus consensus from the call commentary.
- "guidance_change" reflects forward guidance for the next quarter or full year.
- "margin_direction" reflects gross or operating margin commentary.
- "sector_tone" reflects what management said about end-market conditions.
- "confidence" is your confidence in the classification, 10 = very confident, 1 = noisy/contradictory.

Return JSON only. No prose, no explanation, no markdown fences.

TRANSCRIPT:
```

## Why it's built this way

- **Categorical fields, not numbers.** The Faroutman lesson (ch06/ch10):
  never let Claude produce a number that reaches the broker. Claude labels;
  Python computes.
- **`max_tokens=200`.** Caps the response so Claude can't wrap prose around
  the JSON and break `json.loads` (ch05).
- **Integer confidence.** Easier to threshold, harder to over-tune than a
  continuous probability.

## How the output is consumed (deterministic)

`score_classification()` counts bullish vs bearish fields:
confidence < 7 → skip · ≥3 bullish + 0 bearish → long ×1.0 · 2/0 → long ×0.5 ·
mirrored for shorts · anything mixed → skip. The 3-of-4 threshold absorbs a
single misclassified field by design.

## Offline stub behavior

Without `ANTHROPIC_API_KEY`, `framework/claude.py` answers this prompt with a
deterministic keyword classifier over the transcript text (beat/miss,
raised/cut/withdrawn, expand/contract, tone words) so the pipeline runs
end-to-end offline. Schema-identical to the real thing; announced once per
process.

## Cost (ch11 math)

A transcript is ~8–15k input tokens + 200 output → **$0.03–0.05 per event**
on Sonnet ($3/M in, $15/M out). One inference per event; most events score
"skip", so cost per *traded* event is a little higher.

---
*Educational reference. Not financial advice. See [DISCLAIMER.md](../../DISCLAIMER.md).*
