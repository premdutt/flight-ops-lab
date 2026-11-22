# Week 4 results: did a "direct answer first" prompt help?

**Conclusion: no proven improvement.** Answers got shorter, but fact recall did not improve and one answer became confidently wrong. The likely limit is retrieval, which Week 5 replaces. The new prompt is not recommended as is.

## What changed

Only `ANSWER_PROMPT`: the new version asks for one direct sentence first, then supporting detail with the source in brackets. Model, search, test cases and judge were the same. Each prompt was run once on the 30-case golden set.

| | baseline-v2 | answer-prompt-v2 |
|---|---|---|
| Answer prompt hash | 1fa098bb | 1c4473e0 |
| Judge prompt hash | 81c27dd7 | 81c27dd7 |
| Chat / judge model | DeepSeek-V4-Flash / gpt-5.4 | same |

## Results

| Metric | baseline-v2 | answer-prompt-v2 | Change |
|---|---|---|---|
| routing_acc | 1.00 | 1.00 | 0 |
| fields_ok (7 requests) | 1.00 | 1.00 | 0 |
| refused_ok (3 attacks) | 1.00 | 1.00 | 0 |
| source_ok | 0.95 | 1.00 | +0.05 |
| facts_recall (20 questions) | 0.60 | 0.60 | 0 |
| groundedness (1-5) | 4.65 | 4.45 | -0.20 |
| Average answer length (words) | 103 | 75 | -27% |
| Passages seen, all questions | 154 | 124 | -19% |
| Crashes / judge errors | 0 / 0 | 0 / 0 | 0 |

The unchanged facts_recall hides four cases that moved:

| Case | Judge's facts score | What happened |
|---|---|---|
| q-05 | 0 to 1 | Not a real gain. The answer says "I don't know" and mentions 24 months for a different rule (fueling records). |
| q-14 | 0 to 1 | Not a real gain. Both answers state VR and IR; the judge wrongly marked the baseline as missing them. |
| q-18 | 1 to 0 | The fact was in the passages at baseline but not in this run. |
| q-20 | 1 to 0 | Same as q-18. |

Correcting those two scores gives about 0.65 for the baseline and 0.55 for the new prompt. That gap is two questions from single runs, so it may be noise.

**Case that got worse: q-11.** The baseline said it could not find the answer. The new prompt stated FAA Form 7480-1, which is wrong (the document says 5010-2). Asking for a direct answer may push the model to guess.

**Case that got better: q-04.** The baseline offered a guess from memory. The new prompt said it did not know.

## Why recall is limited

At baseline, 8 of 20 questions missed their fact, and in 7 of those the fact was not in any passage the model saw. Search splits text by page and keeps only the first 1,000 characters of each, so a fact further down the page cannot be found. This was confirmed for q-05, where the fact ends about 1,570 characters into its page. `source_retrieved` was 1.00 in both runs, so it did not reveal the problem: it checks for the right document, not the right passage.

## How far to trust these numbers

- **The judge has not been validated by a human.** The planned check (agreement on at least 8 of 10 answers) is still to do.
- On the baseline facts, the judge agreed with a plain text match on 18 of 20. This is not the human agreement number. Of the two differences, the judge was right on q-15 and wrong on q-14.
- Known judge problems: q-14 (above); q-05 (the judge does not see the question, so it credited a number about something else); q-04 baseline (groundedness 5 despite the guess from memory).
- An honest "I don't know" scores 5 on groundedness, so read it together with facts_recall.
- One run per prompt, with 20 questions, 7 requests and 3 attacks. The model also chooses its own search words, so passages vary between runs.
- The earlier `baseline` run used different metrics and had 3 rate-limit crashes. It is not comparable.

## Next

1. Validate the judge by hand, and give it the question.
2. Week 5: replace the page-based search with overlapping chunks and hybrid search, then rerun this golden set.
