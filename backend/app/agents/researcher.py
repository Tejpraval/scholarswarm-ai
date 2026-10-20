"""Agent 2: Scholarship Researcher — discovers real opportunities via web search."""
from __future__ import annotations
import logging
import time
import json
import hashlib
import re
from typing import List, Optional, Dict, Any
from typing import Callable
from datetime import datetime, timezone
from urllib.parse import urlsplit
from pydantic import ValidationError

from app.models.student import StudentProfile
from app.models.scholarship import ScholarshipOpportunity, SourceType, FundingType, VerificationStatus
from app.models.agent_io import ResearchResponse
from app.models.workflow import AgentEvent, AgentStatus
from app.agents.state import GraphState
from app.utils.llm import call_llm
from app.utils.search import search_web
from app.utils.event_bus import publish_agent_event

logger = logging.getLogger(__name__)

AGENT_NAME = "scholarship_researcher"
MAX_ATTEMPTS = 3  # initial structured call plus at most two corrective retries


def _canonical_search_url(url: Optional[str]) -> str:
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    return f"{(parsed.hostname or '').lower()}:{parsed.path.rstrip('/').lower()}"


class InvalidResearchOutput(ValueError):
    """The LLM response was not a usable scholarship array."""

    def __init__(self, message: str, failure_kind: str = "schema_failure"):
        super().__init__(message)
        self.failure_kind = failure_kind


def _emit(state: GraphState, status: AgentStatus, message: str,
          details: Optional[Dict] = None, error: Optional[str] = None) -> AgentEvent:
    ev = AgentEvent(
        run_id=state.run_id,
        agent_name=AGENT_NAME,
        status=status,
        message=message,
        details=details,
        error=error,
    )
    state.events.append(ev)
    publish_agent_event(ev)
    logger.info(f"[{AGENT_NAME}] {status.value}: {message}")
    return ev


def _stable_id(name: str, provider: str, country: str) -> str:
    """Create a stable deduplication ID from key scholarship fields."""
    key = f"{name.lower().strip()}|{provider.lower().strip()}|{country.lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _build_search_queries(profile: StudentProfile) -> List[str]:
    """Build targeted search queries based on student profile."""
    destinations = profile.destination_preferences or ["Canada", "Germany", "Singapore"]
    field = profile.target_field or "Computer Science AI Machine Learning"
    degree_value = getattr(profile.target_degree, "value", profile.target_degree)
    degree_terms = {
        "bachelors": "bachelor's undergraduate",
        "masters": "master's postgraduate",
        "phd": "PhD doctoral",
        "postdoc": "postdoctoral",
    }
    degree = degree_terms.get(str(degree_value).lower(), "postgraduate")
    nationality = profile.nationality or "international"

    queries = []
    current_year = datetime.now().year
    next_year = current_year + 1
    for dest in destinations:
        queries.append(
            f"fully funded {degree} scholarship {field} {dest} international students "
            f"{nationality} {current_year} {next_year}"
        )
        queries.append(
            f"{dest} university {degree} scholarship {field} {nationality} students "
            f"deadline {current_year} {next_year}"
        )

    # Add well-known programmes only for destinations the student selected.
    selected = {destination.casefold() for destination in destinations}
    if "germany" in selected:
        queries.append(
            f"DAAD scholarship Germany {degree} {field} {nationality} {current_year} {next_year}"
        )
    if "singapore" in selected:
        queries.append(
            f"Singapore scholarship {degree} {field} international students {current_year} {next_year}"
        )
        queries.append(
            f"NTU scholarship Singapore {degree} {field} international students {current_year} {next_year}"
        )
    if "canada" in selected:
        queries.append(
            f"Canada graduate scholarship {degree} international students {nationality} {current_year} {next_year}"
        )
        queries.append(
            f"Ontario Graduate Scholarship international students {field} {current_year} {next_year}"
        )
        queries.append(
            f"Mitacs graduate funding Canada international students {current_year} {next_year}"
        )

    return queries[:12]  # Cap at 12 queries to avoid excessive API calls


async def _parse_opportunities_from_search(
    query: str,
    results: List[Dict[str, Any]],
    profile: StudentProfile,
    on_retry: Optional[Callable[[], None]] = None,
    on_provider_retry: Optional[Callable[[], None]] = None,
) -> List[ScholarshipOpportunity]:
    """Use LLM to parse search results into structured opportunities."""
    if not results:
        return []

    results_text = "\n\n".join([
        f"Title: {r.get('title', 'Unknown')}\nURL: {r.get('url', '')}\nSnippet: {r.get('content', r.get('snippet', ''))}"
        for r in results[:5]
    ])

    prompt = f"""You are a scholarship data extractor for an AI research system.
Given these web search results about scholarships for: "{query}"

Student context:
- Nationality: {profile.nationality or 'Indian'}
- Degree applying for: {profile.target_degree or 'Masters'}
- Field: {profile.target_field or 'Computer Science / AI'}
- CGPA: {profile.academic.cgpa or 'Not specified'}/{profile.academic.cgpa_scale or 10.0}
- Destination preferences: {', '.join(profile.destination_preferences) if profile.destination_preferences else 'Canada, Germany, Singapore'}

Search results:
{results_text}

Extract ONLY distinct scholarship/funding opportunities you can identify from these results.
Return a JSON array of objects. For each, include ONLY what the source text explicitly states.
For every finding, set source_url to the exact URL copied from the matching search result above. Do not invent, rewrite, normalize, or omit this URL.
Use null for any field not mentioned in the source.
Do NOT invent funding amounts, deadlines, or requirements.

Format:
[
  {{
    "name": "Official scholarship name",
    "provider": "Organization providing the scholarship",
    "country": "Country of study",
    "university": "Specific university or null",
    "source_type": "university|government|foundation|corporate|unknown",
    "degree_levels": ["masters", "phd", etc],
    "fields_of_study": ["Computer Science", "AI", etc],
    "funding_type": "full_funding|partial_funding|stipend_only|tuition_only|living_allowance|unknown",
    "funding_description": "Description from source or empty string",
    "funding_amount_usd": null,
    "covers_tuition": null,
    "covers_living": null,
    "min_cgpa": null,
    "required_language_tests": [],
    "citizenship_restrictions": [],
    "open_to_indian_nationals": null,
    "application_deadline": null,
    "deadline_notes": "",
    "official_url": "URL if mentioned",
    "source_url": "URL of this search result",
    "source_snippet": "Relevant text excerpt (max 200 chars)",
    "application_instructions": "",
    "required_documents": []
  }}
]

Return ONLY a JSON object with an "opportunities" array. If no valid opportunities are found, return {{"opportunities": []}}.
Be conservative — only include opportunities that the text clearly describes."""

    try:
        raw = await call_llm(
            prompt, temperature=0.1, max_tokens=2000,
            response_schema=ResearchResponse,
            on_retry=on_provider_retry,
        )
        response = None
        for attempt in range(MAX_ATTEMPTS):
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            try:
                response = ResearchResponse.model_validate_json(cleaned.strip())
                break
            except ValidationError as e:
                error_types = {item["type"] for item in e.errors()}
                failure_kind = "malformed_json" if "json_invalid" in error_types else "schema_failure"
                parse_error = str(e).splitlines()[0][:240]

            if attempt + 1 >= MAX_ATTEMPTS:
                raise InvalidResearchOutput(parse_error, failure_kind)
            if on_retry:
                on_retry()
            logger.warning(
                "Structured research output invalid; retrying (attempt %s/%s, %s)",
                attempt + 2, MAX_ATTEMPTS, failure_kind,
            )
            raw = await call_llm(
                prompt + f"\nYour previous response failed strict validation: {parse_error}. "
                "Correct that issue and return ONLY a valid JSON object matching the schema; "
                "do not use markdown fences or commentary.",
                temperature=0.0,
                max_tokens=2000,
                response_schema=ResearchResponse,
                on_retry=on_provider_retry,
            )

        opportunities = []
        result_by_url = {
            _canonical_search_url(item.get("url")): item
            for item in results if item.get("url")
        }
        for item in response.opportunities:
            source_key = _canonical_search_url(item.source_url)
            if source_key not in result_by_url:
                source_key = _canonical_search_url(item.official_url)
            if not source_key or source_key not in result_by_url:
                continue
            source_url = result_by_url[source_key].get("url", "")
            try:
                opp = ScholarshipOpportunity(
                    id=_stable_id(
                        item.name, item.provider, item.country
                    ),
                    name=item.name,
                    provider=item.provider,
                    source_type=SourceType(item.source_type),
                    country=item.country,
                    university=item.university,
                    degree_levels=item.degree_levels,
                    fields_of_study=item.fields_of_study,
                    funding_type=FundingType(item.funding_type),
                    funding_description=item.funding_description,
                    funding_amount_usd=item.funding_amount_usd,
                    covers_tuition=item.covers_tuition,
                    covers_living=item.covers_living,
                    min_cgpa=item.min_cgpa,
                    required_language_tests=item.required_language_tests,
                    citizenship_restrictions=item.citizenship_restrictions,
                    open_to_indian_nationals=item.open_to_indian_nationals,
                    application_deadline=item.application_deadline,
                    deadline_notes=item.deadline_notes,
                    official_url=None,
                    source_url=source_url,
                    source_snippet=result_by_url[source_key].get("content", "")[:300],
                    retrieved_at=datetime.now(timezone.utc),
                    verification_status=VerificationStatus.UNVERIFIED,
                    application_instructions=item.application_instructions,
                    required_documents=item.required_documents,
                )
                opportunities.append(opp)
            except Exception as e:
                logger.warning(f"Failed to parse opportunity: {e}, item={item}")
                continue
        if response.opportunities and not opportunities:
            raise InvalidResearchOutput(
                "LLM findings did not cite a URL returned by the search provider",
                "invalid_findings",
            )
        return opportunities

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed for research results: {e}")
        raise InvalidResearchOutput("LLM returned invalid JSON") from e
    except InvalidResearchOutput:
        raise
    except Exception as e:
        logger.warning(f"LLM parse failed: {e}")
        raise


def _deduplicate(opportunities: List[ScholarshipOpportunity]) -> List[ScholarshipOpportunity]:
    """Remove exact and known-program-alias duplicates, keeping the richer record."""
    seen = {}
    alias_index = {}
    title_index = {}
    deduped = []
    for opp in opportunities:
        normalized_title = re.sub(r"[^a-z0-9]", "", opp.name.casefold())
        normalized_title = re.sub(r"(scholarships?|awards?|funding|programmes?|programs?)", "", normalized_title)
        normalized_title = re.sub(r"20\d{2}", "", normalized_title)
        title_key = f"{opp.country.casefold()}:{normalized_title}"
        provider_aliases = set(re.findall(r"\b[A-Z][A-Z0-9]{3,}\b", opp.provider))
        name_aliases = set(re.findall(r"\b[A-Z][A-Z0-9]{3,}\b", opp.name))
        aliases = name_aliases - provider_aliases - {"ASEAN", "EUROPEAN"}
        alias_key = next((f"{opp.country.lower()}:{alias}" for alias in sorted(aliases)
                          if f"{opp.country.lower()}:{alias}" in alias_index), None)
        duplicate_id = opp.id if opp.id in seen else None
        existing_index = alias_index.get(alias_key) if alias_key else None
        exact_title_index = title_index.get(title_key) if normalized_title else None
        if duplicate_id is None and existing_index is None and exact_title_index is None:
            seen[opp.id] = opp
            index = len(deduped)
            if normalized_title:
                title_index[title_key] = index
            for alias in aliases:
                alias_index[f"{opp.country.lower()}:{alias}"] = index
            deduped.append(opp)
        else:
            index = existing_index if existing_index is not None else exact_title_index if exact_title_index is not None else next(
                i for i, existing in enumerate(deduped) if existing.id == duplicate_id
            )
            existing = deduped[index]
            # Prefer the record with more corroborating fields, retaining its identity.
            old_completeness = sum(bool(getattr(existing, field)) for field in (
                "official_url", "application_deadline", "funding_description",
                "degree_levels", "source_snippet", "source_url",
            ))
            new_completeness = sum(bool(getattr(opp, field)) for field in (
                "official_url", "application_deadline", "funding_description",
                "degree_levels", "source_snippet", "source_url",
            ))
            if new_completeness > old_completeness:
                opp.id = existing.id
                deduped[index] = opp
            for alias in aliases:
                alias_index[f"{opp.country.lower()}:{alias}"] = index
            if normalized_title:
                title_index[title_key] = index
    return deduped


async def run_researcher(state: GraphState) -> GraphState:
    """Main researcher agent node."""
    _emit(state, AgentStatus.RUNNING, "Starting scholarship discovery via web research")
    start = time.time()

    profile = state.enriched_profile or state.student_profile
    if not profile:
        _emit(state, AgentStatus.FAILED, "No student profile available for research",
              error="missing_profile")
        state.research_error = "No student profile to base research on"
        return state

    queries = _build_search_queries(profile)
    state.research_queries_used = queries
    _emit(state, AgentStatus.RUNNING,
          f"Generated {len(queries)} search queries for {', '.join(profile.destination_preferences or ['Canada','Germany','Singapore'])}",
          details={"queries": queries})

    all_opportunities: List[ScholarshipOpportunity] = []
    failed_queries = 0
    failed_llm_calls = 0
    malformed_outputs = 0
    schema_failures = 0
    invalid_findings = 0
    structured_retries = 0
    provider_retries = 0
    provider_failure_kinds: Dict[str, int] = {}

    def increment_structured_retries():
        nonlocal structured_retries
        structured_retries += 1

    def increment_provider_retries():
        nonlocal provider_retries
        provider_retries += 1

    for i, query in enumerate(queries):
        _emit(state, AgentStatus.RUNNING,
              f"Searching [{i + 1}/{len(queries)}]: {query[:80]}...")
        try:
            results = await search_web(query, max_results=5)
        except Exception as e:
            failed_queries += 1
            logger.error(f"Search query failed: {query[:50]} — {e}")
            _emit(state, AgentStatus.RETRYING,
                  f"Search failed for query {i + 1}, continuing with other queries",
                  error=type(e).__name__)

            if failed_queries >= 3:
                state.research_error = (
                    f"Web search provider failed on {failed_queries} queries. "
                    "Results may be incomplete. Check your TAVILY_API_KEY."
                )
                _emit(state, AgentStatus.RETRYING,
                      "Multiple search failures detected — results may be partial",
                      error=state.research_error)
                break
            continue

        if not results:
            _emit(state, AgentStatus.RUNNING, f"Query {i + 1}: no results returned")
            continue

        try:
            opps = await _parse_opportunities_from_search(
                query, results, profile,
                on_retry=increment_structured_retries,
                on_provider_retry=increment_provider_retries,
            )
            all_opportunities.extend(opps)
            _emit(state, AgentStatus.RUNNING,
                  f"Query {i + 1}: found {len(opps)} opportunities from {len(results)} results",
                  details={
                      "query": query,
                      "results_count": len(results),
                      "result_urls": [r.get("url") for r in results if r.get("url")],
                      "opps_found": len(opps),
                  })
        except InvalidResearchOutput as e:
            if e.failure_kind == "malformed_json":
                malformed_outputs += 1
            elif e.failure_kind == "invalid_findings":
                invalid_findings += 1
            else:
                schema_failures += 1
            logger.warning("Structured research output %s for query %s", e.failure_kind, i + 1)
            _emit(state, AgentStatus.RETRYING,
                  f"Research model returned {e.failure_kind} for query {i + 1}; continuing",
                  details={"failure_kind": e.failure_kind}, error=type(e).__name__)
        except Exception as e:
            failed_llm_calls += 1
            failure_kind = getattr(e, "failure_kind", "provider_unavailable")
            provider_failure_kinds[failure_kind] = provider_failure_kinds.get(failure_kind, 0) + 1
            logger.warning("Research model call failed for query %s (%s)", i + 1, failure_kind)
            _emit(state, AgentStatus.RETRYING,
                  f"Research model unavailable for query {i + 1}; continuing with other searches",
                  details={"failure_kind": failure_kind}, error=type(e).__name__)

    # Deduplicate
    unique_opps = _deduplicate(all_opportunities)
    duration_ms = int((time.time() - start) * 1000)

    state.discovered_opportunities = unique_opps
    state.completed_agents.append(AGENT_NAME)

    if failed_queries and not state.research_error:
        state.research_error = f"{failed_queries} web search query/queries failed; available results may be incomplete."
    invalid_outputs = malformed_outputs + schema_failures
    if invalid_outputs:
        state.research_error = (state.research_error + " " if state.research_error else "") + (
            f"{malformed_outputs} malformed JSON response(s), {schema_failures} schema-invalid response(s) after bounded retries."
        )
    if invalid_findings:
        state.research_error = (state.research_error + " " if state.research_error else "") + (
            f"{invalid_findings} response(s) contained no finding linked to an actual search result."
        )
    if failed_llm_calls:
        if provider_failure_kinds.get("quota_exhausted"):
            failure_text = (
                f"Gemini daily request quota was exhausted for {provider_failure_kinds['quota_exhausted']} "
                "research call(s); remaining queries were preserved as partial results."
            )
        elif provider_failure_kinds.get("invalid_credentials"):
            failure_text = (
                f"Gemini rejected credentials on {provider_failure_kinds['invalid_credentials']} "
                "research call(s); check the configured key."
            )
        elif provider_failure_kinds.get("transient_provider_error"):
            failure_text = (
                f"Gemini rate limited {provider_failure_kinds['transient_provider_error']} research call(s) "
                "after bounded retries; valid results from other queries were preserved."
            )
        else:
            failure_text = f"{failed_llm_calls} research model call(s) failed after bounded retries."
        state.research_error = (state.research_error + " " if state.research_error else "") + failure_text

    if len(unique_opps) == 0 and failed_queries > 0:
        _emit(state, AgentStatus.FAILED,
              "No opportunities discovered — search provider may be unavailable",
              error=state.research_error)
    else:
        _emit(state, AgentStatus.COMPLETED,
              f"Research complete: {len(unique_opps)} unique opportunities discovered "
              f"({len(all_opportunities)} raw, {len(all_opportunities) - len(unique_opps)} duplicates removed)",
              details={
                  "total_discovered": len(unique_opps),
                  "raw_count": len(all_opportunities),
                  "failed_queries": failed_queries,
                  "provider_failures": failed_llm_calls,
                  "provider_failure_kinds": provider_failure_kinds,
                  "provider_retries": provider_retries,
                  "malformed_json_failures": malformed_outputs,
                  "schema_failures": schema_failures,
                  "invalid_findings": invalid_findings,
                  "structured_retries": structured_retries,
                  "queries_run": len(queries),
              })
        state.events[-1].duration_ms = duration_ms

    return state
