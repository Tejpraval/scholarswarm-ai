import { useEffect, useState, useCallback } from 'react';
import {
  Sparkles, Play, RefreshCw, AlertCircle, CheckCircle,
  Activity, Search, Database
} from 'lucide-react';
import { startRun, startDemoRun, getRunStatus, getRunResults, createEventStream, retryRun } from '../api/client';
import { AgentStatusCard } from '../components/AgentStatusCard';
import type { AgentEvent, WorkflowResults } from '../types';
import type { AgentState } from '../stores/appStore';
import { INITIAL_AGENTS } from '../stores/appStore';

interface Props {
  profileId: string;
  profileName: string;
  mode: 'demo' | 'live';
  onResultsReady: (results: WorkflowResults, runId: string) => void;
}

export function DashboardPage({ profileId, profileName, mode, onResultsReady }: Props) {
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'completed' | 'failed' | 'partial'>('idle');
  const [agents, setAgents] = useState<AgentState[]>(INITIAL_AGENTS);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statsCount, setStatsCount] = useState({ discovered: 0, verified: 0, retries: 0 });
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  const updateAgent = useCallback((event: AgentEvent) => {
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

    // Update stats from event details
    if (event.details) {
      const d = event.details as Record<string, number>;
      if (d.total_discovered !== undefined) setStatsCount(p => ({ ...p, discovered: d.total_discovered }));
      if (d.eligible !== undefined || d.potentially_eligible !== undefined) {
        setStatsCount(p => ({
          ...p,
          verified: d.eligible || 0
        }));
      }
    }
    if (event.status === 'retrying') {
      setStatsCount(p => ({ ...p, retries: p.retries + 1 }));
    }
  }, []);

  const recoverRun = async (id: string) => {
    let lastConnectionError: unknown;
    for (let attempt = 0; attempt < 300; attempt++) {
      try {
        const status = await getRunStatus(id);
        const state = String(status.status ?? '');
        if (state === 'completed' || state === 'partial') {
          return await getRunResults(id);
        }
        if (state === 'failed') {
          throw new Error(String(status.error || status.workflow_error || 'Workflow failed.'));
        }
      } catch (err) {
        if (err instanceof Error && err.message !== 'Failed to fetch') throw err;
        lastConnectionError = err;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    if (lastConnectionError) throw new Error('Could not reconnect to the backend to retrieve this run.');
    throw new Error('The run is still in progress. Return to the dashboard and check again shortly.');
  };

  const watchRun = (id: string) => {
    eventSource?.close();
    const es = createEventStream(
      id,
      (event) => {
        setEvents(prev => [...prev, event]);
        updateAgent(event);
      },
      async () => {
        es.close();
        try {
          const results = await getRunResults(id);
          setRunStatus('completed');
          onResultsReady(results, id);
        } catch {
          try {
            const results = await recoverRun(id);
            setRunStatus('completed');
            onResultsReady(results, id);
          } catch (err) {
            setRunStatus('failed');
            setError(err instanceof Error ? err.message : 'Could not load run results.');
          }
        }
      },
      async () => {
        es.close();
        setError('Live updates disconnected. Checking the run status…');
        try {
          const results = await recoverRun(id);
          setRunStatus('completed');
          setError(null);
          onResultsReady(results, id);
        } catch (err) {
          setRunStatus('failed');
          setError(err instanceof Error ? err.message : 'Workflow failed.');
        }
      }
    );
    setEventSource(es);
  };

  const handleStart = async () => {
    setError(null);
    setEvents([]);
    setAgents(INITIAL_AGENTS);
    setStatsCount({ discovered: 0, verified: 0, retries: 0 });
    setRunStatus('running');

    try {
      const runResult = mode === 'demo'
        ? await startDemoRun(profileId)
        : await startRun(profileId);
      const newRunId = runResult.run_id;
      setRunId(newRunId);
      watchRun(newRunId);
    } catch (e: unknown) {
      setRunStatus('failed');
      setError(e instanceof Error ? e.message : 'Failed to start workflow');
    }
  };

  const handleRetry = async () => {
    if (mode === 'demo' || !runId) return handleStart();
    try {
      const result = await retryRun(runId);
      setRunId(result.new_run_id);
      setRunStatus('running');
      setAgents(INITIAL_AGENTS);
      setEvents([]);
      setError(null);
      watchRun(result.new_run_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Retry failed');
    }
  };

  useEffect(() => {
    return () => {
      eventSource?.close();
    };
  }, [eventSource]);

  const isRunning = runStatus === 'running';
  const completedCount = agents.filter(a => a.status === 'completed').length;

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-teal-500 to-blue-600 flex items-center justify-center">
              <Sparkles size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">ScholarSwarm AI</h1>
              <p className="text-xs text-slate-500">Agent Execution Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
            <span>{profileName}</span>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left: Launch area */}
          <div className="lg:col-span-2 space-y-4">
            <div className="rounded-2xl border border-slate-700/50 bg-slate-900/60 p-6">
              <h2 className="text-lg font-bold text-white mb-1">{mode === 'demo' ? 'Curated Demonstration' : 'Live Research Workflow'}</h2>
              <p className="text-sm text-slate-400 mb-5">
                {mode === 'demo'
                  ? 'Prepared official-source dataset; results are curated, not live AI discoveries. Gemini and Tavily are not called.'
                  : `Four AI agents will use live providers to discover and assess opportunities for ${profileName}. API failures will not fall back to demo data.`}
              </p>
              <div data-testid="active-mode" className={`mb-4 rounded-lg border px-3 py-2 text-xs ${mode === 'demo' ? 'border-teal-700/50 bg-teal-950/20 text-teal-300' : 'border-blue-700/50 bg-blue-950/20 text-blue-300'}`}>
                {mode === 'demo' ? 'DEMO MODE — curated dataset, no provider calls' : 'LIVE RESEARCH — real Tavily and Gemini requests'}
              </div>

              {runStatus === 'idle' && (
                <button
                  onClick={handleStart}
                  className="w-full py-4 rounded-xl bg-gradient-to-r from-teal-600 to-blue-600 text-white font-bold text-base hover:from-teal-500 hover:to-blue-500 transition-all flex items-center justify-center gap-2 shadow-lg shadow-teal-900/30"
                >
                  <Play size={18} className="fill-white" />
                  {mode === 'demo' ? 'Load Curated Demo Results' : 'Find Scholarships with Live Research'}
                </button>
              )}

              {isRunning && (
                <div className="w-full py-4 rounded-xl bg-blue-950/40 border border-blue-800/50 text-blue-300 font-semibold text-base flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
                  Agents working...
                </div>
              )}

              {(runStatus === 'completed' || runStatus === 'partial') && (
                <div className="space-y-2">
                  <div className="w-full py-3 rounded-xl bg-teal-950/30 border border-teal-700/50 text-teal-300 font-medium text-sm flex items-center justify-center gap-2">
                    <CheckCircle size={16} />
                    Research Complete
                  </div>
                  <button
                    onClick={handleStart}
                    className="w-full py-2.5 rounded-xl border border-slate-700/50 text-slate-400 text-sm hover:text-slate-200 hover:border-slate-600 transition-colors flex items-center justify-center gap-2"
                  >
                    <RefreshCw size={14} />
                    Run Again
                  </button>
                </div>
              )}

              {runStatus === 'failed' && (
                <div className="space-y-2">
                  <button
                    onClick={handleRetry}
                    className="w-full py-3.5 rounded-xl bg-gradient-to-r from-orange-700 to-red-700 text-white font-semibold text-sm hover:from-orange-600 hover:to-red-600 transition-all flex items-center justify-center gap-2"
                  >
                    <RefreshCw size={16} />
                    Retry Workflow
                  </button>
                </div>
              )}

              {error && (
                <div className="mt-4 p-3 rounded-xl bg-red-950/20 border border-red-800/40 flex items-start gap-2">
                  <AlertCircle size={14} className="text-red-400 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-red-300 leading-relaxed">{error}</p>
                </div>
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-3 text-center">
                <div className="flex items-center justify-center mb-1">
                  <Search size={14} className="text-blue-400" />
                </div>
                <div className="text-xl font-bold text-white">{statsCount.discovered}</div>
                <div className="text-xs text-slate-500">Found</div>
              </div>
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-3 text-center">
                <div className="flex items-center justify-center mb-1">
                  <Database size={14} className="text-teal-400" />
                </div>
                <div className="text-xl font-bold text-white">{statsCount.verified}</div>
                <div className="text-xs text-slate-500">Confirmed eligible</div>
              </div>
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-3 text-center">
                <div className="flex items-center justify-center mb-1">
                  <RefreshCw size={14} className="text-yellow-400" />
                </div>
                <div className="text-xl font-bold text-white">{statsCount.retries}</div>
                <div className="text-xs text-slate-500">Retries</div>
              </div>
            </div>

            {/* Progress */}
            {isRunning && mode === 'live' && (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/40 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400">Overall Progress</span>
                  <span className="text-xs text-slate-400">{completedCount}/4 agents</span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-teal-500 to-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${(completedCount / 4) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Right: Agent cards + event log */}
          <div className="lg:col-span-3 space-y-4">
            {/* Demo fixture progress describes dataset work, not AI agent execution. */}
            {mode === 'demo' ? (
              <div className="rounded-2xl border border-teal-700/40 bg-slate-900/40 p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Activity size={16} className="text-teal-400" />
                  <h3 className="text-sm font-semibold text-slate-200">Curated Fixture Progress</h3>
                </div>
                <p className="text-xs text-slate-500">These steps load prepared evidence and are not represented as AI agent execution.</p>
                {events.length > 0 && <p className="mt-3 text-xs text-teal-300">{events.length} fixture progress events received</p>}
              </div>
            ) : (
            /* Live agent status cards */
            <div className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-5">
              <div className="flex items-center gap-2 mb-4">
                <Activity size={16} className="text-teal-400" />
                <h3 className="text-sm font-semibold text-slate-200">Agent Pipeline</h3>
              </div>
              <div className="space-y-3">
                {agents.map((agent, i) => (
                  <AgentStatusCard key={agent.name} agent={agent} index={i} />
                ))}
              </div>
            </div>
            )}

            {/* Live event log */}
            {events.length > 0 && (
              <div className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
                  <h3 className="text-sm font-semibold text-slate-200">Live Activity</h3>
                  <span className="ml-auto text-xs text-slate-600">{events.length} events</span>
                </div>
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {[...events].reverse().slice(0, 30).map((ev) => (
                    <div key={ev.id} className="flex items-start gap-2 text-xs">
                      <span className={`flex-shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full mt-1.5 ${
                        ev.status === 'completed' ? 'bg-teal-400' :
                        ev.status === 'failed' ? 'bg-red-400' :
                        ev.status === 'retrying' ? 'bg-yellow-400' :
                        'bg-blue-400'
                      }`} />
                      <span className="text-slate-500 flex-shrink-0 font-mono">
                        {new Date(ev.timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                      <span className={`flex-shrink-0 font-medium ${
                        ev.agent_name === 'student_profiler' ? 'text-purple-400' :
                        ev.agent_name === 'scholarship_researcher' ? 'text-blue-400' :
                        ev.agent_name === 'eligibility_verifier' ? 'text-yellow-400' :
                        ev.agent_name === 'matching_agent' ? 'text-teal-400' :
                        'text-slate-500'
                      }`}>
                        [{ev.agent_name.replace('_', ' ').slice(0, 10)}]
                      </span>
                      <span className="text-slate-400 line-clamp-1">{ev.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
