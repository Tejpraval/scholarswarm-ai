// Global application state using React's built-in state + context pattern
// Avoids heavy state libraries while keeping things organized

import { useState, useCallback } from 'react';
import type { StudentProfile, AgentEvent, WorkflowResults, AgentStatusType } from '../types';

export type AppView = 'onboarding' | 'dashboard' | 'results' | 'detail' | 'sop';

export interface AgentState {
  name: string;
  label: string;
  status: AgentStatusType;
  lastMessage: string;
  retryCount: number;
  durationMs?: number;
}

export const AGENT_LABELS: Record<string, string> = {
  student_profiler: 'Student Profiler',
  scholarship_researcher: 'Scholarship Researcher',
  eligibility_verifier: 'Eligibility Verifier',
  matching_agent: 'Matching & Application',
  orchestrator: 'Orchestrator',
  output_validator: 'Output Validator',
};

export const INITIAL_AGENTS: AgentState[] = [
  { name: 'student_profiler', label: 'Student Profiler', status: 'pending', lastMessage: 'Waiting to start...', retryCount: 0 },
  { name: 'scholarship_researcher', label: 'Scholarship Researcher', status: 'pending', lastMessage: 'Waiting...', retryCount: 0 },
  { name: 'eligibility_verifier', label: 'Eligibility Verifier', status: 'pending', lastMessage: 'Waiting...', retryCount: 0 },
  { name: 'matching_agent', label: 'Matching & Application', status: 'pending', lastMessage: 'Waiting...', retryCount: 0 },
];

export function useAppState() {
  const [view, setView] = useState<AppView>('onboarding');
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string>('idle');
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [results, setResults] = useState<WorkflowResults | null>(null);
  const [selectedScholarshipId, setSelectedScholarshipId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const addEvent = useCallback((event: AgentEvent) => {
    setEvents(prev => [...prev, event]);

    // Update agent state
    setAgents(prev => prev.map(agent => {
      if (agent.name === event.agent_name) {
        return {
          ...agent,
          status: event.status,
          lastMessage: event.message,
          retryCount: event.status === 'retrying' ? agent.retryCount + 1 : agent.retryCount,
          durationMs: event.duration_ms ?? agent.durationMs,
        };
      }
      return agent;
    }));
  }, []);

  const resetRun = useCallback(() => {
    setRunId(null);
    setRunStatus('idle');
    setAgents(INITIAL_AGENTS);
    setEvents([]);
    setResults(null);
    setError(null);
  }, []);

  return {
    view, setView,
    profile, setProfile,
    profileId, setProfileId,
    runId, setRunId,
    runStatus, setRunStatus,
    agents, setAgents,
    events,
    addEvent,
    results, setResults,
    selectedScholarshipId, setSelectedScholarshipId,
    error, setError,
    isLoading, setIsLoading,
    resetRun,
  };
}
