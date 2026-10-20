import { useState } from 'react';
import {
  Trophy, Globe, AlertCircle, Info,
  List, Star, FileText, ArrowLeft, ExternalLink, CheckCircle,
  XCircle, HelpCircle, Shield
} from 'lucide-react';
import { ScholarshipCard } from '../components/ScholarshipCard';
import type { WorkflowResults, MatchResult, ApplicationDraft } from '../types';

interface Props {
  results: WorkflowResults;
  runId: string;
  profileName: string;
  mode: 'demo' | 'live';
  onBack: () => void;
}

type Tab = 'top5' | 'all' | 'sop';

// Remove unused ELIGIBILITY_ICONS constant (now inlined in DetailPanel)


function DetailPanel({ match, onClose }: { match: MatchResult; onClose: () => void }) {
  const opp = match.scholarship;
  const eli = match.eligibility;
  if (!opp) return null;
  const requirementChecks = eli?.requirement_checks ?? [];
  const missingDocuments = eli?.missing_documents ?? [];
  const missingInfo = eli?.missing_info ?? [];
  const nextActions = match.next_actions ?? [];

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center overflow-y-auto py-8 px-4">
      <div className="w-full max-w-2xl bg-slate-900 rounded-2xl border border-slate-700/60 shadow-2xl">
        {/* Header */}
        <div className="p-5 border-b border-slate-800/60 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-white">{opp.name}</h2>
            <p className="text-sm text-slate-400 mt-0.5">{opp.provider} · {opp.country}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1">
            <XCircle size={20} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Match Score breakdown */}
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Match Score Breakdown</h3>
            <div className="space-y-2">
              {Object.entries(match.score_breakdown ?? {}).map(([key, val]) => (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-40 flex-shrink-0 capitalize">
                    {key.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-teal-500 rounded-full"
                      style={{ width: `${Math.min(100, (val / 30) * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-slate-300 w-8 text-right">{val.toFixed(1)}</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-600 mt-2">Total: {match.match_score.toFixed(1)}/100 — Score reflects match quality, not confirmed eligibility</p>
          </div>

          <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-800/60 bg-slate-950/40 p-3 text-xs">
            <p className="text-slate-400">Opportunity: <span className="text-slate-200">{opp.discovery_status || 'discovered'}</span></p>
            <p className="text-slate-400">Official source: <span className="text-slate-200">{opp.official_source_status || 'unknown'}</span></p>
            <p className="text-slate-400">Requirements: <span className="text-slate-200">{opp.requirements_status || 'unknown'}</span></p>
            <p className="text-slate-400">Deadline: <span className="text-slate-200">{opp.deadline_status || 'unknown'}</span></p>
            <p className="col-span-2 text-slate-400">Eligibility: <span className="text-slate-200">{match.eligibility_status}</span></p>
          </div>

          {/* Eligibility checklist */}
          {eli && requirementChecks.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Eligibility Checklist</h3>
              <div className="space-y-2">
                {requirementChecks.map((check, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <div className="flex-shrink-0 mt-0.5">
                      {check.status === 'met' ? <CheckCircle size={14} className="text-teal-400" /> :
                       check.status === 'not_met' ? <XCircle size={14} className="text-red-400" /> :
                       <HelpCircle size={14} className="text-blue-400" />}
                    </div>
                    <div>
                      <p className="text-slate-300 font-medium text-xs">{check.requirement}</p>
                      {check.student_value && (
                        <p className="text-xs text-slate-500">
                          Yours: <span className="text-slate-400">{check.student_value}</span>
                          {check.required_value && <> · Required: <span className="text-slate-400">{check.required_value}</span></>}
                        </p>
                      )}
                      {check.evidence && (
                        <p className="text-xs text-slate-600 mt-0.5 italic">{check.evidence}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Missing info */}
          {eli && (missingDocuments.length > 0 || missingInfo.length > 0) && (
            <div className="p-3 rounded-xl bg-yellow-950/20 border border-yellow-800/40">
              <h3 className="text-xs font-semibold text-yellow-400 mb-2 flex items-center gap-1">
                <AlertCircle size={12} /> Action Required
              </h3>
              {missingDocuments.map((doc, i) => (
                <p key={i} className="text-xs text-yellow-300/80">📄 {doc}</p>
              ))}
              {missingInfo.map((info, i) => (
                <p key={i} className="text-xs text-yellow-300/80">ℹ️ {info}</p>
              ))}
            </div>
          )}

          {/* Next actions */}
          {nextActions.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Suggested Next Steps</h3>
              <ul className="space-y-1.5">
                {nextActions.map((action, i) => (
                  <li key={i} className="text-xs text-slate-400 flex items-start gap-2">
                    <span className="text-teal-500 flex-shrink-0">→</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Source info */}
          <div className="pt-3 border-t border-slate-800/50">
            <div className="flex items-center justify-between text-xs text-slate-600">
              <span>
                {opp.retrieved_at
                  ? `Retrieved: ${new Date(opp.retrieved_at).toLocaleDateString()}`
                  : 'Retrieval date unknown'}
              </span>
              <span className={
                opp.verification_status === 'verified' ? 'text-teal-500' :
                opp.verification_status === 'partial' ? 'text-yellow-500' :
                'text-slate-600'
              }>
                {opp.verification_status}
              </span>
            </div>
            {(opp.official_url || opp.source_url) && (
              <a
                href={opp.official_url || opp.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-teal-400 hover:text-teal-300 mt-1.5"
              >
                <ExternalLink size={11} />
                {opp.official_source_status === 'verified'
                  ? 'View fetched official source'
                  : 'View discovery source (not official-verified)'}
              </a>
            )}
            {opp.application_url ? (
              <a
                href={opp.application_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-blue-300 hover:text-blue-200 mt-2"
              >
                <ExternalLink size={11} /> Official application route
              </a>
            ) : (
              <p className="text-xs text-slate-500 mt-2">Application route: {opp.application_url_status || 'not published'}</p>
            )}
            {opp.verification_date && (
              <p className="text-xs text-slate-600 mt-1">Fixture source checked: {opp.verification_date}</p>
            )}
            {opp.source_snippet && (
              <p className="text-xs text-slate-600 mt-2 italic line-clamp-2">
                "{opp.source_snippet}"
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SOPPanel({ draft }: { draft: ApplicationDraft }) {
  const [copied, setCopied] = useState(false);
  const placeholders = draft.placeholders ?? [];

  const handleCopy = () => {
    navigator.clipboard.writeText(draft.draft_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([draft.draft_text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SOP_${draft.scholarship_name.replace(/\s+/g, '_')}_DRAFT.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Warning banner */}
      <div className="p-4 rounded-xl bg-yellow-950/20 border border-yellow-800/40 flex items-start gap-3">
        <AlertCircle size={16} className="text-yellow-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-yellow-300">Draft Document — Not for Direct Submission</p>
          <p className="text-xs text-yellow-600 mt-0.5">
            Review all <span className="font-mono text-yellow-500">[PLACEHOLDER]</span> tokens and replace them with your actual information before submitting.
          </p>
        </div>
      </div>

      {/* Placeholders */}
      {placeholders.length > 0 && (
        <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-800/40">
          <p className="text-xs font-semibold text-blue-400 mb-2">Placeholders to fill ({placeholders.length})</p>
          <div className="flex flex-wrap gap-1.5">
            {placeholders.map(p => (
              <code key={p} className="px-2 py-1 rounded bg-slate-800 text-xs text-orange-300">[{p}]</code>
            ))}
          </div>
        </div>
      )}

      {/* Draft text */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/60">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/50">
          <div>
            <p className="text-sm font-semibold text-slate-200">{draft.scholarship_name}</p>
            <p className="text-xs text-slate-500">{draft.word_count} words</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700/50 text-xs text-slate-300 hover:text-white transition-colors"
            >
              {copied ? '✓ Copied' : 'Copy'}
            </button>
            <button
              onClick={handleDownload}
              className="px-3 py-1.5 rounded-lg bg-teal-900/60 border border-teal-700/50 text-xs text-teal-300 hover:text-teal-100 transition-colors"
            >
              Download .txt
            </button>
          </div>
        </div>
        <pre className="p-5 text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">
          {draft.draft_text}
        </pre>
      </div>

      {/* Facts used */}
      {(draft.facts_used ?? []).length > 0 && (
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-700/40">
          <p className="text-xs font-semibold text-slate-500 mb-2">Facts used from your profile</p>
          <div className="space-y-1">
            {(draft.facts_used ?? []).map((f, i) => (
              <p key={i} className="text-xs text-slate-500">✓ {f}</p>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {(draft.warnings ?? []).length > 0 && (
        <div className="space-y-1">
          {(draft.warnings ?? []).map((w, i) => (
            <p key={i} className="text-xs text-yellow-600/80 flex items-center gap-1">
              <AlertCircle size={10} /> {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function ResultsPage({ results, profileName, mode, onBack }: Props) {
  const [tab, setTab] = useState<Tab>('top5');
  const [selectedMatch, setSelectedMatch] = useState<MatchResult | null>(null);
  const safeResults = results ?? ({} as WorkflowResults);
  const scholarships = Array.isArray(safeResults.scholarships) ? safeResults.scholarships : [];
  const topMatches = Array.isArray(safeResults.top_matches) ? safeResults.top_matches : [];
  const allMatches = Array.isArray(safeResults.all_matches) ? safeResults.all_matches : [];
  const discoveredCount = safeResults.discovered_count ?? scholarships.length;
  const sourceCount = scholarships.filter(s => s.official_source_status === 'verified').length;
  const requirementsCount = scholarships.filter(s => s.requirements_status === 'verified').length;

  const tabs = [
    { id: 'top5' as Tab, label: `Top ${topMatches.length}`, icon: Star, count: topMatches.length },
    { id: 'all' as Tab, label: 'All Found', icon: List, count: allMatches.length },
    { id: 'sop' as Tab, label: 'SOP Draft', icon: FileText, count: safeResults.sop_draft ? 1 : 0 },
  ];

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-200 transition-colors"
            >
              <ArrowLeft size={16} />
              <span>New Search</span>
            </button>
            <div className="w-px h-5 bg-slate-700" />
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-teal-500 to-blue-600 flex items-center justify-center">
                <Trophy size={14} className="text-white" />
              </div>
              <div>
                <h1 className="text-base font-bold text-white">Scholarship Results</h1>
                <p className="text-xs text-slate-500">{profileName}</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <div className="flex items-center gap-1.5">
              <Globe size={12} />
              <span>{discoveredCount} found</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Shield size={12} />
              <span>{sourceCount} official sources · {requirementsCount} requirements verified</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {mode === 'demo' && (
          <div data-testid="curated-demo-banner" className="mb-5 rounded-xl border border-teal-700/50 bg-teal-950/20 px-4 py-3 text-sm text-teal-200">
            Curated demonstration data - not live AI discoveries. Source snapshots verified {safeResults.verified_on || 'on the date shown in each source record'}.
          </div>
        )}
        {mode === 'live' && (
          <div data-testid="live-results-banner" className="mb-5 rounded-xl border border-blue-700/50 bg-blue-950/20 px-4 py-3 text-sm text-blue-200">
            Live Research results - verify current details at each official source before applying.
          </div>
        )}
        {/* Summary banner */}
        <div className="mb-6 p-5 rounded-2xl border border-slate-700/50 bg-gradient-to-br from-slate-900 to-navy-950/30">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-xl font-bold text-white mb-1">
                {topMatches.length > 0
                  ? `${topMatches.length} Recommended Opportunities`
                  : 'Research Complete'}
              </h2>
              <p className="text-sm text-slate-400">
                {discoveredCount} total opportunities researched ·
                {allMatches.length} ranked ·
                {safeResults.sop_draft ? ' SOP drafted' : ' No SOP generated'}
              </p>
            </div>
            {safeResults.workflow_error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-yellow-950/30 border border-yellow-800/40">
                <AlertCircle size={14} className="text-yellow-400" />
                <span className="text-xs text-yellow-300">Partial results — some errors occurred</span>
              </div>
            )}
          </div>

          {safeResults.research_error && (
            <div className="mt-3 p-3 rounded-xl bg-red-950/20 border border-red-800/40">
              <p className="text-xs text-red-300 flex items-center gap-1.5">
                <AlertCircle size={12} /> {safeResults.research_error}
              </p>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-slate-900/60 p-1 rounded-xl border border-slate-700/40 w-fit">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                tab === t.id
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              <t.icon size={14} />
              <span>{t.label}</span>
              {t.count > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                  tab === t.id ? 'bg-teal-900/60 text-teal-300' : 'bg-slate-800 text-slate-500'
                }`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'top5' && (
          <div>
            {topMatches.length === 0 ? (
              <div className="text-center py-16">
                <Info size={32} className="mx-auto mb-3 text-slate-600" />
                <p className="text-slate-400">No top matches found for your profile.</p>
                <p className="text-sm text-slate-600 mt-1">
                  This may be due to incomplete profile information or search limitations.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {topMatches.map(match => (
                  <ScholarshipCard
                    key={match.id}
                    match={match}
                    isTop
                    onClick={() => setSelectedMatch(match)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'all' && (
          <div className="space-y-3">
            <p className="text-xs text-slate-600 mb-4">
              All {allMatches.length} discovered opportunities, ranked by match score.
              Eligibility and match score are independent — a high score does not mean confirmed eligibility.
            </p>
            {allMatches.map(match => (
              <ScholarshipCard
                key={match.id}
                match={match}
                isTop={false}
                onClick={() => setSelectedMatch(match)}
              />
            ))}
            {allMatches.length === 0 && (
              <div className="text-center py-16">
                <Globe size={32} className="mx-auto mb-3 text-slate-600" />
                <p className="text-slate-400">No opportunities were discovered in this run.</p>
                <p className="text-sm text-slate-600 mt-1">Check that your TAVILY_API_KEY is configured correctly.</p>
              </div>
            )}
          </div>
        )}

        {tab === 'sop' && (
          <div>
            {safeResults.sop_draft ? (
              <SOPPanel draft={safeResults.sop_draft} />
            ) : (
              <div className="text-center py-16">
                <FileText size={32} className="mx-auto mb-3 text-slate-600" />
                <p className="text-slate-400">No SOP draft was generated for this run.</p>
                <p className="text-sm text-slate-600 mt-1">This may occur if no suitable matching opportunity was found.</p>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Detail modal */}
      {selectedMatch && (
        <DetailPanel match={selectedMatch} onClose={() => setSelectedMatch(null)} />
      )}
    </div>
  );
}
