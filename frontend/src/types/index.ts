// ScholarSwarm AI — TypeScript Type Definitions

export type DegreeLevel = 'bachelors' | 'masters' | 'phd' | 'postdoc';
export type FundingPreference = 'full_funding' | 'partial_funding' | 'any';
export type EligibilityStatus = 'eligible' | 'potentially_eligible' | 'ineligible' | 'needs_verification';
export type AgentStatusType = 'pending' | 'running' | 'completed' | 'failed' | 'retrying' | 'skipped';
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'partial';
export type FundingType = 'full_funding' | 'partial_funding' | 'stipend_only' | 'tuition_only' | 'living_allowance' | 'unknown';
export type VerificationStatus = 'verified' | 'unverified' | 'partial' | 'failed';
export type EvidenceStage = 'not_checked' | 'verified' | 'partial' | 'unknown' | 'unavailable';

export interface AcademicProfile {
  degree_level?: DegreeLevel;
  degree_name?: string;
  institution?: string;
  cgpa?: number;
  cgpa_scale?: number;
  graduation_year?: number;
  major?: string;
  country_of_study?: string;
  language_scores?: Record<string, number | string>;
}

export interface DocumentUpload {
  id: string;
  doc_type: 'resume' | 'marksheet' | 'other';
  filename: string;
  extraction_status: 'pending' | 'done' | 'failed';
  uploaded_at: string;
}

export interface StudentProfile {
  id: string;
  name: string;
  email?: string;
  nationality?: string;
  country_of_residence?: string;
  academic: AcademicProfile;
  skills: string[];
  projects: Array<{ name: string; description: string; technologies?: string[]; source?: string }>;
  achievements: string[];
  work_experience: Array<Record<string, string>>;
  research_interests: string[];
  destination_preferences: string[];
  target_degree?: DegreeLevel;
  target_field?: string;
  funding_preference: FundingPreference;
  budget_usd_per_year?: number;
  github_url?: string;
  personal_statement_notes?: string;
  profile_completeness: number;
  missing_fields: string[];
  documents: DocumentUpload[];
  created_at: string;
  updated_at: string;
}

export interface ProfileCreateRequest {
  name: string;
  email?: string;
  nationality?: string;
  country_of_residence?: string;
  degree_level?: DegreeLevel;
  degree_name?: string;
  institution?: string;
  cgpa?: number;
  cgpa_scale?: number;
  graduation_year?: number;
  major?: string;
  skills?: string[];
  research_interests?: string[];
  destination_preferences?: string[];
  target_degree?: DegreeLevel;
  target_field?: string;
  funding_preference?: FundingPreference;
  budget_usd_per_year?: number;
  github_url?: string;
  personal_statement_notes?: string;
}

export interface RequirementCheck {
  category?: string;
  requirement: string;
  student_value?: string;
  required_value?: string;
  status: 'met' | 'not_met' | 'unknown' | 'partially_met' | 'not_applicable';
  evidence?: string;
  source_url?: string;
}

export interface EligibilityAssessment {
  id: string;
  scholarship_id: string;
  student_id: string;
  status: EligibilityStatus;
  confidence: number;
  requirement_checks: RequirementCheck[];
  missing_documents: string[];
  missing_info: string[];
  disqualifying_factors: string[];
  notes: string;
  source_verified: boolean;
  eligibility_assessed?: boolean;
  assessed_at: string;
}

export interface ScholarshipOpportunity {
  id: string;
  name: string;
  provider: string;
  source_type: string;
  country: string;
  university?: string;
  degree_levels: string[];
  fields_of_study: string[];
  funding_type: FundingType;
  funding_amount_usd?: number;
  funding_description: string;
  covers_tuition?: boolean;
  covers_living?: boolean;
  covers_travel?: boolean;
  min_cgpa?: number;
  required_language_tests: string[];
  citizenship_restrictions: string[];
  open_to_indian_nationals?: boolean;
  application_deadline?: string;
  deadline_notes: string;
  official_url?: string;
  application_url?: string;
  application_url_status?: string;
  verification_date?: string;
  official_source_urls?: string[];
  source_url: string;
  source_snippet: string;
  retrieved_at?: string;
  verification_status: VerificationStatus;
  discovery_status?: string;
  official_source_status?: EvidenceStage;
  requirements_status?: EvidenceStage;
  deadline_status?: EvidenceStage;
  application_instructions: string;
  required_documents: string[];
}

export interface MatchResult {
  id: string;
  scholarship_id: string;
  student_id: string;
  rank: number;
  match_score: number;
  eligibility_status: EligibilityStatus;
  eligibility_confidence: number;
  score_breakdown: Record<string, number>;
  match_explanation: string;
  why_recommended: string;
  scholarship?: ScholarshipOpportunity;
  eligibility?: EligibilityAssessment;
  missing_requirements: string[];
  next_actions: string[];
  ranked_at: string;
}

export interface ApplicationDraft {
  id: string;
  run_id: string;
  student_id: string;
  scholarship_id: string;
  scholarship_name: string;
  university?: string;
  draft_text: string;
  placeholders: string[];
  word_count: number;
  is_draft: boolean;
  facts_used: string[];
  warnings: string[];
  generated_at: string;
}

export interface AgentEvent {
  id: string;
  run_id: string;
  agent_name: string;
  status: AgentStatusType;
  message: string;
  details?: Record<string, unknown>;
  error?: string;
  timestamp: string;
  duration_ms?: number;
}

export interface WorkflowResults {
  run_id: string;
  discovered_count: number;
  scholarships: ScholarshipOpportunity[];
  top_matches: MatchResult[];
  all_matches: MatchResult[];
  sop_draft?: ApplicationDraft;
  workflow_error?: string;
  research_error?: string;
  run_mode?: 'live' | 'curated_demo';
  demo_dataset_id?: string;
  verified_on?: string;
}

export interface SSEMessage {
  type: 'event' | 'status' | 'complete' | 'error' | 'heartbeat';
  data?: AgentEvent | Record<string, unknown>;
}
