# Pramaan

Pramaan is a Streamlit app for checking viral health claims in English or Hindi against search results. It extracts claim keywords, searches for research and reporting, and presents a transparent, link-backed evidence summary. It is intended to help families, elderly people, and non-English speakers pause and review sources before sharing health claims.

## Search engines

The app uses three SerpApi engines:

1. `google_scholar` for up to 10 research results, searched with the claim keywords plus `clinical trial`.
2. `google_news` for up to 8 news results using the keywords.
3. `google` for up to 8 organic results using the keywords plus `fact check myth`.

Requests are cached in `cache/` using an MD5 digest of the engine and query. Cached responses are reused on later checks.

## Evidence Meter

The meter counts Scholar results whose title/snippet/publication summary contains strong terms (`randomized`, `clinical trial`, `meta-analysis`, `systematic review`, `cohort`, `human`, `patients`) and weak-study terms (`mice`, `rats`, `in vitro`, `animal`, `preliminary`, `pilot`). Papers are tagged Human trial, Review, Animal-Lab, or Unclear using the same transparent keyword rules.

News and web result titles/snippets are checked for `fake`, `myth`, `false`, `misleading`, `no evidence`, `debunk`, `hoax`, and `unproven`. The UI shows the match counts and the verdict thresholds. This is a simple text-matching heuristic, not an assessment of study quality or medical consensus. Explanation sentences link to a result, and the app does not generate claims beyond its retrieved sources and rule counts.

Verdicts:

- **Supported**: at least 3 strong Scholar matches, with no weak-study or debunk-word matches.
- **Mixed**: at least one strong Scholar match and a debunk-word match, or at least one strong Scholar match with weak-study matches at least as numerous as strong matches.
- **Weak**: results exist but the other thresholds are not met.
- **No evidence**: no usable results were returned.

## Setup

Requires Python 3.10 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SERPAPI_KEY = "your SerpApi key"
streamlit run app.py
```

Alternatively, enter the SerpApi key in the password field in the sidebar. The key is not stored in the app source. Enable **Use saved sample data** to try synthetic, illustrative turmeric records without an API key or credits. Their titles, details, and `example.org` links only demonstrate the response layout; they are not live results or evidence for any claim.

## Limitations

Search results can be incomplete, biased, outdated, or unrelated. Keyword matching can miss context, and a search result mentioning a study does not establish that a claim is true. Hindi keyword extraction preserves Devanagari tokens but uses a compact stopword list, so its results may be imperfect. This app is not medical advice; consult a doctor for health decisions.

AI tools used: Copilot SDK in VS Code for code generation.
