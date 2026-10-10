import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import streamlit as st
from serpapi import GoogleSearch


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
SAMPLE_FILE = BASE_DIR / "samples" / "sample_turmeric.json"

ENGLISH_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "did", "do", "does", "doing", "down",
    "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "will", "with", "you", "your", "yours", "yourself",
    "yourselves", "cures", "cure", "treats", "treat", "helps", "help", "can",
    "will", "every", "regular",
}
HINDI_STOPWORDS = {
    "और", "का", "की", "के", "को", "से", "में", "पर", "है", "हैं", "था", "थी",
    "थे", "हो", "होता", "होती", "होते", "यह", "वह", "इस", "उस", "जो", "कि",
    "एक", "नहीं", "भी", "तो", "तक", "लिए", "द्वारा", "अपने", "अपनी", "अपना",
    "कर", "करता", "करती", "करते", "खाने", "रोज़", "रोज",
}
STRONG_TERMS = (
    "randomized", "clinical trial", "meta-analysis", "systematic review",
    "cohort", "human", "patients",
)
WEAK_TERMS = ("mice", "rats", "in vitro", "animal", "preliminary", "pilot")
DEBUNK_TERMS = (
    "fake", "myth", "false", "misleading", "no evidence", "debunk", "hoax",
    "unproven",
)
REVIEW_TERMS = ("meta-analysis", "systematic review", "review")
ANIMAL_TERMS = ("mice", "rats", "in vitro", "animal")


def extract_keywords(claim: str) -> list[str]:
    """Keep up to six distinct Latin or Devanagari terms after stopword removal."""
    tokens = re.findall(r"[a-z0-9]+|[\u0900-\u097f]+", claim.lower())
    keywords: list[str] = []
    for token in tokens:
        if token not in ENGLISH_STOPWORDS and token not in HINDI_STOPWORDS:
            if token not in keywords:
                keywords.append(token)
        if len(keywords) == 6:
            break
    return keywords


def load_cached_search(engine: str, query: str, api_key: str) -> dict[str, Any]:
    cache_id = hashlib.md5(f"{engine}+{query}".encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{cache_id}.json"
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data

    params = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
        "num": 10 if engine == "google_scholar" else 8,
    }
    response = GoogleSearch(params).get_dict()
    if not isinstance(response, dict):
        raise ValueError("SerpApi returned an unexpected response format.")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with cache_file.open("w", encoding="utf-8") as handle:
        json.dump(response, handle, ensure_ascii=False, indent=2)
    return response


def results_for(response: dict[str, Any], key: str) -> list[dict[str, Any]]:
    results = response.get(key, [])
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def joined_text(item: dict[str, Any]) -> str:
    publication_info = item.get("publication_info", {})
    summary = publication_info.get("summary", "") if isinstance(publication_info, dict) else ""
    parts = [item.get("title", ""), item.get("snippet", ""), summary]
    return " ".join(str(part) for part in parts if part).lower()


def classify_paper(paper: dict[str, Any]) -> str:
    text = joined_text(paper)
    if any(term in text for term in ANIMAL_TERMS):
        return "Animal-Lab"
    if any(term in text for term in REVIEW_TERMS):
        return "Review"
    if any(term in text for term in ("randomized", "clinical trial", "human", "patients", "cohort")):
        return "Human trial"
    return "Unclear"


def matches_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def parse_year(paper: dict[str, Any]) -> str:
    info = paper.get("publication_info", {})
    summary = info.get("summary", "") if isinstance(info, dict) else ""
    match = re.search(r"\b(19|20)\d{2}\b", str(summary))
    return match.group(0) if match else ""


def citation_count(paper: dict[str, Any]) -> str:
    links = paper.get("inline_links", {})
    cited = links.get("cited_by", {}) if isinstance(links, dict) else {}
    return str(cited.get("total", "")) if isinstance(cited, dict) else ""


def parse_result_date(value: str) -> datetime:
    now = datetime.now(timezone.utc)
    normalized = value.strip().lower()
    relative = re.search(r"(\d+)\s+(hour|day|week|month|year)s?\s+ago", normalized)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        days = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}[unit]
        return now - timedelta(days=amount * days)
    for candidate in (value, value.replace(" at ", " ")):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            continue
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=timezone.utc)


def result_link(item: dict[str, Any], fallback_query: str) -> str:
    link = item.get("link")
    if isinstance(link, str) and link.startswith(("https://", "http://")):
        return link
    return f"https://www.google.com/search?q={quote_plus(fallback_query)}"


def evidence_verdict(
    papers: list[dict[str, Any]],
    news: list[dict[str, Any]],
    search_results: list[dict[str, Any]],
) -> tuple[str, int, int, int]:
    strong_count = sum(matches_any(joined_text(paper), STRONG_TERMS) for paper in papers)
    weak_count = sum(matches_any(joined_text(paper), WEAK_TERMS) for paper in papers)
    debunk_count = sum(
        matches_any(joined_text(item), DEBUNK_TERMS)
        for item in [*news, *search_results]
    )
    total = len(papers) + len(news) + len(search_results)
    if total == 0:
        verdict = "❌ No evidence"
    elif strong_count > 0 and (debunk_count > 0 or weak_count >= strong_count):
        verdict = "🟡 Mixed"
    elif strong_count >= 3 and weak_count == 0 and debunk_count == 0:
        verdict = "✅ Supported"
    elif strong_count == 0:
        verdict = "🟠 Weak"
    else:
        verdict = "🟠 Weak"
    return verdict, int(strong_count), int(weak_count), int(debunk_count)


def show_linked_explanation(
    verdict: str,
    strong: int,
    weak: int,
    debunk: int,
    papers: list[dict[str, Any]],
    news: list[dict[str, Any]],
    search_results: list[dict[str, Any]],
    query: str,
) -> str:
    if verdict.startswith("✅"):
        sentence = (
            f"The rules found {strong} Scholar result(s) with strong-evidence terms, "
            f"{weak} with weak-study terms, and {debunk} news/search result(s) with debunk terms."
        )
        source = next((p for p in papers if matches_any(joined_text(p), STRONG_TERMS)), None)
    elif verdict.startswith("🟡"):
        sentence = (
            f"The results are mixed by these rules: {strong} Scholar result(s) match strong terms, "
            f"{weak} match weak-study terms, and {debunk} news/search result(s) match debunk terms."
        )
        source = next(
            (item for item in [*news, *search_results] if matches_any(joined_text(item), DEBUNK_TERMS)),
            papers[0] if papers else None,
        )
    elif verdict.startswith("🟠"):
        sentence = (
            f"The rules found {strong} Scholar result(s) with strong-evidence terms, "
            f"{weak} with weak-study terms, and {debunk} news/search result(s) with debunk terms; "
            "these keyword counts are not a clinical assessment."
        )
        source = papers[0] if papers else (news[0] if news else (search_results[0] if search_results else None))
    else:
        sentence = "No results were returned by the three searches, so this check cannot assess the claim."
        source = None
    url = result_link(source, query) if source else f"https://www.google.com/search?q={quote_plus(query)}"
    st.markdown(f"[{sentence}]({url})")
    return sentence


def explain_api_error(error: Exception) -> str:
    message = str(error).lower()
    if any(term in message for term in ("invalid api key", "api_key is invalid", "unauthorized", "401")):
        return "The SerpApi key was rejected. Check the key in the sidebar or your SERPAPI_KEY environment variable."
    if any(term in message for term in ("quota", "out of searches", "searches_left", "monthly limit", "429")):
        return "The SerpApi account appears to have exhausted its available searches or reached a rate limit."
    return f"SerpApi request failed: {error}"


def main() -> None:
    st.set_page_config(page_title="Pramaan — Health Claim Checker", page_icon="🔎", layout="wide")
    st.title("Pramaan")
    st.caption("A transparent, source-linked first look at viral health claims.")
    with st.sidebar:
        st.header("Search settings")
        api_key = st.text_input(
            "SerpApi API key",
            value=os.environ.get("SERPAPI_KEY", ""),
            type="password",
            help="Read from SERPAPI_KEY or enter it here. The key is never included in the app source.",
        )
        demo_mode = st.checkbox("Use saved sample data", value=False)
        st.caption("Sample mode uses a fixed turmeric example and makes no API calls.")

    examples = [
        "Warm water with turmeric cures diabetes",
        "Regular exercise lowers blood pressure",
        "रोज़ लहसुन खाने से कैंसर ठीक हो जाता है",
    ]
    st.subheader("Try an example")
    columns = st.columns(3)
    for index, (column, example) in enumerate(zip(columns, examples)):
        if column.button(example, key=f"example_{index}", use_container_width=True):
            st.session_state["claim_input"] = example
    claim = st.text_area(
        "Paste a health claim (English or Hindi)",
        key="claim_input",
        height=90,
        placeholder="For example: Warm water with turmeric cures diabetes",
    )
    submitted = st.button("Check claim", type="primary")
    st.caption("Not medical advice. Consult a doctor.")
    if not submitted:
        return
    if not claim.strip():
        st.warning("Enter a health claim to get started.")
        return

    keywords = extract_keywords(claim)
    if not keywords:
        st.warning("No searchable keywords were found. Try a longer claim with specific terms.")
        return
    st.subheader("Claim breakdown")
    st.write(" · ".join(keywords))

    query_terms = " ".join(keywords)
    scholar_query = f"{query_terms} clinical trial"
    news_query = query_terms
    fact_query = f"{query_terms} fact check myth"

    if demo_mode:
        try:
            with SAMPLE_FILE.open("r", encoding="utf-8") as handle:
                sample = json.load(handle)
            scholar_response = sample["google_scholar"]
            news_response = sample["google_news"]
            fact_response = sample["google"]
            st.info(
                "Showing synthetic illustrative turmeric records to demonstrate the layout. "
                "They are not live results or evidence for the claim you entered."
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            st.error(f"Could not load the saved sample data: {error}")
            return
    else:
        if not api_key.strip():
            st.error("Add your SerpApi key in the sidebar or set SERPAPI_KEY, then submit again.")
            return
        responses: dict[str, dict[str, Any]] = {}
        failures: list[str] = []
        requests = [
            ("google_scholar", scholar_query),
            ("google_news", news_query),
            ("google", fact_query),
        ]
        for engine, query in requests:
            try:
                responses[engine] = load_cached_search(engine, query, api_key.strip())
            except Exception as error:
                failures.append(f"{engine}: {explain_api_error(error)}")
        if failures:
            for failure in failures:
                st.error(failure)
            if len(responses) != 3:
                st.warning("Some searches did not complete; the verdict below uses only the results that were returned.")
        scholar_response = responses.get("google_scholar", {})
        news_response = responses.get("google_news", {})
        fact_response = responses.get("google", {})
        for engine, response in (
            ("Google Scholar", scholar_response),
            ("Google News", news_response),
            ("Google Search", fact_response),
        ):
            if response.get("error"):
                st.error(f"{engine}: {explain_api_error(RuntimeError(str(response['error'])))}")

    papers = results_for(scholar_response, "organic_results")
    news = results_for(news_response, "news_results")
    search_results = results_for(fact_response, "organic_results")

    st.subheader("Evidence Meter")
    st.caption(
        "Transparent keyword heuristic: Scholar strong terms are randomized, clinical trial, "
        "meta-analysis, systematic review, cohort, human, patients; weak terms are mice, rats, "
        "in vitro, animal, preliminary, pilot. News and web results are checked for fake, myth, "
        "false, misleading, no evidence, debunk, hoax, unproven. These terms are clues, not proof."
    )
    verdict, strong, weak, debunk = evidence_verdict(papers, news, search_results)
    st.markdown(f"### {verdict}")
    st.write(f"Strong Scholar matches: **{strong}** · Weak-study matches: **{weak}** · Debunk-word matches: **{debunk}**")
    st.caption("Verdict thresholds: Supported = at least 3 strong papers and no weak/debunk matches; Mixed = strong and debunk matches, or weak matches at least as numerous as strong; Weak = other non-empty results; No evidence = no returned results.")
    reasoning = show_linked_explanation(
        verdict, strong, weak, debunk, papers, news, search_results, query_terms
    )

    st.subheader("Scholar results")
    if papers:
        table_rows = []
        for paper in papers[:10]:
            table_rows.append(
                {
                    "Title": paper.get("title", "Untitled"),
                    "Link": paper.get("link", ""),
                    "Snippet": paper.get("snippet", ""),
                    "Year": parse_year(paper),
                    "Cited by": citation_count(paper),
                    "Tag": classify_paper(paper),
                }
            )
        st.dataframe(
            table_rows,
            hide_index=True,
            use_container_width=True,
            column_config={"Link": st.column_config.LinkColumn("Source")},
        )
    else:
        st.info("No Scholar papers were returned.")

    st.subheader("News timeline")
    ordered_news = sorted(news, key=lambda item: parse_result_date(str(item.get("date", ""))), reverse=True)
    if ordered_news:
        for item in ordered_news:
            date = str(item.get("date", "Date not provided"))
            source_value = item.get("source", "Source not provided")
            source_name = (
                str(source_value.get("name", "Source not provided"))
                if isinstance(source_value, dict)
                else str(source_value)
            )
            title = str(item.get("title", "Untitled"))
            url = result_link(item, news_query)
            st.markdown(f"- **{date}** · {source_name} · [{title}]({url})")
    else:
        st.info("No news results were returned.")

    with st.expander("Fact-check web results"):
        if search_results:
            for item in search_results:
                title = str(item.get("title", "Untitled"))
                snippet = str(item.get("snippet", ""))
                st.markdown(f"- [{title}]({result_link(item, fact_query)}) — {snippet}")
        else:
            st.info("No organic web results were returned.")

    if not papers and not news and not search_results:
        st.warning("All three searches returned no usable results. Try a more specific claim or check the API status.")

    source_items = [*papers, *news, *search_results]
    top_links: list[tuple[str, str]] = []
    seen_links: set[str] = set()
    for item in source_items:
        url = result_link(item, query_terms)
        if url not in seen_links:
            top_links.append((str(item.get("title", "Source")), url))
            seen_links.add(url)
        if len(top_links) == 2:
            break
    share_lines = [
        "Pramaan — Health claim check",
        f"Claim: {claim.strip()}",
        f"Verdict: {verdict}",
        f"Reasoning: {reasoning}",
        "Top links:",
    ]
    share_lines.extend(f"- {title}: {url}" for title, url in top_links)
    if not top_links:
        share_lines.append(f"- Search: https://www.google.com/search?q={quote_plus(query_terms)}")
    share_text = "\n".join(share_lines)
    st.subheader("Shareable summary")
    st.code(share_text, language=None)
    st.download_button(
        "Download summary (.txt)",
        data=share_text,
        file_name="pramaan-health-claim-check.txt",
        mime="text/plain",
    )


if __name__ == "__main__":
    main()
