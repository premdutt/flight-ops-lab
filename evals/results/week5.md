# Week 5 results: did Azure AI Search fix retrieval?

**Conclusion: yes. Fact recall went from 0.60 to 1.00.** The gain comes from the new chunking: page-sized passages cut at 1,000 characters were replaced by overlapping 1,200-character chunks. Hybrid search scored the same as keyword search on this golden set, which can't tell them apart (see below). Hybrid stays the default.

## What changed

Only the search behind `search_docs`. The model, answer prompt, judge, test cases and the tool's description were the same as in Week 4. Each search mode was run once on the 30-case golden set.

| | baseline-v2 (Week 4) | search-keyword | search-hybrid |
|---|---|---|---|
| Search | Local text files, split by page, first 1,000 chars of each | Azure AI Search, keyword (BM25) | Azure AI Search, keyword + vector |
| Chunks | ~1 per page, cut at 1,000 chars | 225: per page, 1,200 chars, 150 overlap | same |
| `SEARCH_MODE` | `pages` | `keyword` | `hybrid` |
| Answer / judge prompt hash | 1fa098bb / 81c27dd7 | same | same |
| Chat / judge model | DeepSeek-V4-Flash / gpt-5.4 | same | same |

## Results

| Metric | baseline-v2 | search-keyword | search-hybrid |
|---|---|---|---|
| routing_acc | 1.00 | 1.00 | 1.00 |
| fields_ok (7 requests) | 1.00 | 1.00 | 1.00 |
| refused_ok (3 attacks) | 1.00 | 1.00 | 1.00 |
| source_ok | 0.95 | 1.00 | 1.00 |
| **facts_recall (20 questions)** | **0.60** | **1.00** | **1.00** |
| groundedness (1-5) | 4.65 | 4.85 | 4.85 |
| Fact in a passage the model saw | 13/20 | 20/20 | 20/20 |
| Passages seen, all questions | 154 | 80 | 99 |
| Average answer length (words) | 103 | 62 | 57 |
| Crashes / judge errors | 0 / 0 | 0 / 0 | 0 / 0 |

**The judge's 1.00 was checked by a plain text match.** It agrees on 19 of 20 answers in both runs. The difference is q-15, where the answer writes "National Fire Protection Association (NFPA) 407": the fact is there, and the judge is right.

**The Week 4 failures are fixed.** q-05, q-16 and q-17 (facts further down a page), q-11 (the prompt-v2 run said 7480-1; both runs now say 5010-2) and q-04 (the baseline answered from memory).

**The agent now searches once per question.** 80 passages for 20 questions is exactly one search of 4 passages each. In Week 4 the agent kept searching: one traced question made 5 searches and used about 17,900 tokens, close to the chat deployment's per-minute limit. Fewer searches mean fewer tokens, fewer rate-limit errors and shorter answers.

## Keyword vs hybrid

Both modes found every fact, so this set can't separate them. The golden questions use the documents' own wording ("Terminal Control Areas", "intermittent identification"), which is where keyword search is strongest. Vector search helps when users phrase things differently, which these cases don't test.

Differences seen:

- Hybrid made about 5 more searches across the 20 questions (99 passages vs 80).
- In a check before the run, hybrid search with the q-04 question text missed the "magnetic" fact. In the run, the agent searched again and found it, and the answer begins with "I found it. Let me get the exact quote." That narration is visible to the user.

Hybrid stays the default because it is the safer choice for questions not worded like the documents, and the embedding call is cheap (embedding capacity 500). `SEARCH_MODE` keeps the comparison repeatable.

## Remaining issues

- **q-14, groundedness 3 in both runs.** The answer correctly gives VR and IR, then expands them to Visual and Instrument Flight Rules, which is not in the passages. True, but from the model's memory.
- **q-02, groundedness 4 in both runs.** Minor.
- At 1.00, facts_recall can no longer show improvements on this set. Harder cases are needed.

## How far to trust these numbers

- **The judge is still not validated by a human.** The Week 4 check (agreement on at least 8 of 10) is still open. The text-match check above lowers the risk for facts_recall, but not for groundedness.
- One run per mode. The model chooses its own search words, so results vary between runs.
- 20 questions from 3 documents, all worded like the documents.

## Next

1. Add 5-10 reworded questions (for example "How long do we keep driver training paperwork?" for q-05) and rerun keyword vs hybrid.
2. Step 5.8: prove that re-ingesting, editing and deleting documents keep the index correct.
3. Validate the judge by hand, and give it the question.
