# Demo script (about 2:30, recorded locally)

**Setup.** Run `python -m banlag` and open http://127.0.0.1:8765. Optionally, show the test run first: `python -m unittest discover -s tests` ends with "OK".

**Never say:**
- that the AI "knew" or "hid" anything;
- that a webpage is wrong;
- that both citations concern the wrong notice;
- that BANLAG proves an omission, or that it "understands" text;
- that a synthetic sample is a finding.

Anything labelled *experimental* is a machine reading for human review.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:15 | The F08 case file loads | "India prohibited specific drug combinations, one exact composition per notice. BANLAG lets a researcher check what Google's AI answers say about them." |
| 0:15–0:30 | Panel 01: S.O. 3078(E) | "This notice covers exactly Dicyclomine, Paracetamol and Clidinium Bromide, for manufacture, sale and distribution." |
| 0:30–1:30 | Live SerpApi panel, MECHANICAL OBSERVATIONS table, block b1 rows [1] and [2] | "This is a real SerpApi capture. The 'prohibited' sentence cites references 1 and 2, read straight from SerpApi's reference indexes. Reference 2's captured metadata mentions four ingredients. That points to a different notice, 3071, which adds chlordiazepoxide; it's a candidate, from name mentions. Reference 1 is cut off, so it stays unresolved. The pages themselves weren't fetched." |
| 1:30–1:45 | Origin cell and the *experimental* labels | "Parser readings, like this partial-disclosure label, are marked experimental. A human makes the call." |
| 1:45–2:00 | G1 tab | "An earlier preregistered browser study, coded by one person: 7 of 10 answers described current use with no India status." |
| 2:00–2:15 | Integrity tab, row S05 | "A literal check: an AI answer cited notice 3080, but the notice for that combination is 3079." |
| 2:15–2:30 | Verify tab, hostile sample | "Imports never count as verified evidence. Research tool only: no medical advice, no accusations." |
