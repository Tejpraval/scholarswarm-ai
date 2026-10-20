// ScholarSwarm AI API Client

import type {
  StudentProfile,
  ProfileCreateRequest,
  WorkflowResults,
  AgentEvent,
  ApplicationDraft,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api');

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;
    } catch { /* Keep the fallback HTTP status when the body is not JSON. */ }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// ── Health ─────────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{ status: string }> {
  return request('/health');
}

// ── Profiles ───────────────────────────────────────────────────────────────────

export async function createProfile(
  data: ProfileCreateRequest
): Promise<{ profile_id: string; profile: StudentProfile }> {
  return request('/profiles', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getProfile(profileId: string): Promise<StudentProfile> {
  return request(`/profiles/${profileId}`);
}

export async function updateProfile(
  profileId: string,
  data: ProfileCreateRequest
): Promise<{ profile_id: string; profile: StudentProfile }> {
  return request(`/profiles/${profileId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function uploadDocument(
  profileId: string,
  docType: 'resume' | 'marksheet',
  file: File
): Promise<{
  document_id: string;
  doc_type: string;
  filename: string;
  extraction_status: string;
  chars_extracted: number;
  extraction_error?: string;
}> {
  const formData = new FormData();
  formData.append('doc_type', docType);
  formData.append('file', file);

  const response = await fetch(`${BASE_URL}/profiles/${profileId}/documents`, {
    method: 'POST',
    body: formData,
    // Don't set Content-Type — let browser set multipart/form-data with boundary
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch { /* Keep the fallback HTTP status when the body is not JSON. */ }
    throw new ApiError(response.status, detail);
  }

  return response.json();
}

// ── Workflow Runs ──────────────────────────────────────────────────────────────

export async function startRun(
  profileId: string
): Promise<{ run_id: string; student_id: string; status: string; message: string }> {
  return request('/runs', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function startDemoRun(
  profileId: string
): Promise<{ run_id: string; student_id: string; status: string; mode: 'curated_demo'; message: string }> {
  return request('/demo/runs', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function getRunStatus(runId: string): Promise<Record<string, unknown>> {
  return request(`/runs/${runId}`);
}

export async function getRunResults(runId: string): Promise<WorkflowResults> {
  const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

  // The SSE completion and persisted results can become visible a moment apart.
  // A 202 response is valid HTTP, so request() returns its progress object; wait
  // for the actual result shape before handing data to the results page.
  for (let attempt = 0; attempt < 20; attempt++) {
    const payload = await request<Partial<WorkflowResults> & { status?: string; message?: string }>(
      `/runs/${runId}/results`
    );
    if (Array.isArray(payload.top_matches) && Array.isArray(payload.all_matches)) {
      return {
        ...payload,
        run_id: payload.run_id ?? runId,
        discovered_count: payload.discovered_count ?? payload.scholarships?.length ?? 0,
        scholarships: Array.isArray(payload.scholarships)
          ? payload.scholarships.map(scholarship => ({
              ...scholarship,
              degree_levels: scholarship.degree_levels ?? [],
              fields_of_study: scholarship.fields_of_study ?? [],
              required_language_tests: scholarship.required_language_tests ?? [],
              citizenship_restrictions: scholarship.citizenship_restrictions ?? [],
              required_documents: scholarship.required_documents ?? [],
            }))
          : [],
        top_matches: payload.top_matches.map(match => ({
          ...match,
          score_breakdown: match.score_breakdown ?? {},
          missing_requirements: match.missing_requirements ?? [],
          next_actions: match.next_actions ?? [],
          scholarship: match.scholarship ? {
            ...match.scholarship,
            degree_levels: match.scholarship.degree_levels ?? [],
            fields_of_study: match.scholarship.fields_of_study ?? [],
            required_language_tests: match.scholarship.required_language_tests ?? [],
            citizenship_restrictions: match.scholarship.citizenship_restrictions ?? [],
            required_documents: match.scholarship.required_documents ?? [],
          } : undefined,
          eligibility: match.eligibility ? {
            ...match.eligibility,
            requirement_checks: match.eligibility.requirement_checks ?? [],
            missing_documents: match.eligibility.missing_documents ?? [],
            missing_info: match.eligibility.missing_info ?? [],
            disqualifying_factors: match.eligibility.disqualifying_factors ?? [],
          } : undefined,
        })),
        all_matches: payload.all_matches.map(match => ({
          ...match,
          score_breakdown: match.score_breakdown ?? {},
          missing_requirements: match.missing_requirements ?? [],
          next_actions: match.next_actions ?? [],
          scholarship: match.scholarship ? {
            ...match.scholarship,
            degree_levels: match.scholarship.degree_levels ?? [],
            fields_of_study: match.scholarship.fields_of_study ?? [],
            required_language_tests: match.scholarship.required_language_tests ?? [],
            citizenship_restrictions: match.scholarship.citizenship_restrictions ?? [],
            required_documents: match.scholarship.required_documents ?? [],
          } : undefined,
          eligibility: match.eligibility ? {
            ...match.eligibility,
            requirement_checks: match.eligibility.requirement_checks ?? [],
            missing_documents: match.eligibility.missing_documents ?? [],
            missing_info: match.eligibility.missing_info ?? [],
            disqualifying_factors: match.eligibility.disqualifying_factors ?? [],
          } : undefined,
        })),
        sop_draft: payload.sop_draft ? {
          ...payload.sop_draft,
          placeholders: payload.sop_draft.placeholders ?? [],
          facts_used: payload.sop_draft.facts_used ?? [],
          warnings: payload.sop_draft.warnings ?? [],
        } : undefined,
      } as WorkflowResults;
    }
    if (attempt < 19) await wait(500);
  }

  throw new Error('The run finished, but its results are not ready yet. Please try again.');
}

export async function getScholarshipDetail(
  runId: string,
  scholarshipId: string
): Promise<{ scholarship: Record<string, unknown>; eligibility: Record<string, unknown> | null }> {
  return request(`/runs/${runId}/scholarships/${scholarshipId}`);
}

export async function getSopDraft(runId: string): Promise<ApplicationDraft> {
  return request(`/runs/${runId}/sop`, { method: 'POST' });
}

export async function retryRun(
  runId: string
): Promise<{ new_run_id: string; original_run_id: string }> {
  return request(`/runs/${runId}/retry`, { method: 'POST' });
}

// ── SSE Event Streaming ────────────────────────────────────────────────────────

export function createEventStream(runId: string, onEvent: (event: AgentEvent) => void, onComplete: () => void, onError: (err: string) => void): EventSource {
  const es = new EventSource(`${BASE_URL}/runs/${runId}/events`);

  es.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'event' && msg.data) {
        onEvent(msg.data as AgentEvent);
      } else if (msg.type === 'complete') {
        onComplete();
        es.close();
      } else if (msg.type === 'error') {
        onError(msg.data?.error as string || 'Unknown error');
        es.close();
      } else if (msg.type === 'status') {
        const status = (msg.data as { status?: string } | undefined)?.status;
        if (status === 'completed' || status === 'partial') {
          onComplete();
          es.close();
        } else if (status === 'failed') {
          onError('Workflow failed');
          es.close();
        }
      }
      // heartbeat — no action needed
    } catch { /* Ignore malformed individual SSE events and keep the stream alive. */ }
  };

  es.onerror = () => {
    onError('Connection to event stream lost');
    es.close();
  };

  return es;
}

export { ApiError };
