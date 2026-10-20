import React from 'react';
import {
  MapPin, DollarSign, Calendar, ExternalLink, Star,
  CheckCircle, AlertCircle, HelpCircle, XCircle, TrendingUp,
  BookOpen, Shield
} from 'lucide-react';
import type { LucideProps } from 'lucide-react';
import type { MatchResult, EligibilityStatus } from '../types';

type IconComponent = React.ForwardRefExoticComponent<Omit<LucideProps, 'ref'> & React.RefAttributes<SVGSVGElement>>;

interface EligibilityConfig {
  label: string;
  icon: IconComponent;
  color: string;
  bg: string;
}

interface Props {
  match: MatchResult;
  isTop?: boolean;
  onClick?: () => void;
}

const ELIGIBILITY_CONFIG: Record<EligibilityStatus, EligibilityConfig> = {
  eligible: {
    label: 'Eligible',
    icon: CheckCircle,
    color: 'text-teal-400',
    bg: 'bg-teal-950/40 border-teal-800/50',
  },
  potentially_eligible: {
    label: 'Possibly Eligible',
    icon: AlertCircle,
    color: 'text-yellow-400',
    bg: 'bg-yellow-950/30 border-yellow-800/50',
  },
  needs_verification: {
    label: 'Needs Verification',
    icon: HelpCircle,
    color: 'text-blue-400',
    bg: 'bg-blue-950/30 border-blue-800/50',
  },
  ineligible: {
    label: 'Ineligible',
    icon: XCircle,
    color: 'text-red-400',
    bg: 'bg-red-950/20 border-red-800/40',
  },
};

const FUNDING_LABELS: Record<string, string> = {
  full_funding: 'Full Funding',
  partial_funding: 'Partial Funding',
  stipend_only: 'Stipend Only',
  tuition_only: 'Tuition Only',
  living_allowance: 'Living Allowance',
  unknown: 'Funding TBD',
};

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 70 ? '#2dd4bf' : pct >= 45 ? '#facc15' : '#f87171';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-bold" style={{ color }}>{pct.toFixed(0)}</span>
    </div>
  );
}

export function ScholarshipCard({ match, isTop = false, onClick }: Props) {
  const opp = match.scholarship;
  if (!opp) return null;

  const eligConfig = ELIGIBILITY_CONFIG[match.eligibility_status] ?? ELIGIBILITY_CONFIG.needs_verification;
  const EligIcon = eligConfig.icon;

  return (
    <div
      onClick={onClick}
      className={`relative rounded-2xl border transition-all duration-200 overflow-hidden
        ${isTop
          ? 'border-teal-700/60 bg-gradient-to-br from-slate-900 via-navy-950/40 to-slate-900'
          : 'border-slate-700/50 bg-slate-900/60'
        }
        ${onClick ? 'cursor-pointer hover:border-slate-600/80 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5' : ''}
      `}
    >
      {isTop && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-teal-500 via-blue-500 to-teal-500" />
      )}

      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              {isTop && (
                <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-teal-900/60 border border-teal-700/50">
                  <Star size={10} className="text-teal-400 fill-teal-400" />
                  <span className="text-teal-400 text-xs font-semibold">Top Pick #{match.rank}</span>
                </div>
              )}
              {!isTop && (
                <span className="text-xs text-slate-500 font-medium">#{match.rank}</span>
              )}
            </div>
            <h3 className="text-base font-bold text-slate-100 leading-snug line-clamp-2">
              {opp.name}
            </h3>
            <p className="text-sm text-slate-400 mt-0.5">{opp.provider}</p>
          </div>

          {/* Eligibility badge */}
          <div className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold ${eligConfig.bg}`}>
            <EligIcon size={12} className={eligConfig.color} />
            <span className={eligConfig.color}>{eligConfig.label}</span>
          </div>
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap gap-3 mb-3">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <MapPin size={12} className="text-slate-500" />
            <span>{opp.country}</span>
            {opp.university && <span className="text-slate-600">· {opp.university}</span>}
          </div>

          {(opp.funding_type && opp.funding_type !== 'unknown') && (
            <div className={`flex items-center gap-1.5 text-xs font-medium ${
              opp.funding_type === 'full_funding' ? 'text-teal-400' : 'text-slate-400'
            }`}>
              <DollarSign size={12} />
              <span>{FUNDING_LABELS[opp.funding_type]}</span>
            </div>
          )}

          {opp.application_deadline && (
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Calendar size={12} className="text-slate-500" />
              <span>{opp.application_deadline}</span>
            </div>
          )}
        </div>

        {/* Funding coverage */}
        {opp.funding_description && (
          <p className="text-xs text-slate-400 mb-3 line-clamp-2 leading-relaxed">
            {opp.funding_description}
          </p>
        )}

        {/* Score */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-1 text-xs text-slate-500">
              <TrendingUp size={10} />
              <span>Fit score (not eligibility)</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-slate-500">
              <Shield size={10} />
              <span>Confidence: {Math.round(match.eligibility_confidence * 100)}%</span>
            </div>
          </div>
          <ScoreBar score={match.match_score} />
        </div>

        {/* Why recommended */}
        {match.why_recommended && (
          <p className="text-xs text-slate-400 leading-relaxed mb-3 line-clamp-3">
            {match.why_recommended}
          </p>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-800/50">
          <div className="flex items-center gap-3">
            {(opp.degree_levels ?? []).length > 0 && (
              <div className="flex items-center gap-1 text-xs text-slate-500">
                <BookOpen size={11} />
                <span>{(opp.degree_levels ?? []).join(', ')}</span>
              </div>
            )}
            <div className="flex flex-wrap gap-x-2 gap-y-1 text-[10px] text-slate-500">
              <span>Source: {opp.official_source_status ?? 'not checked'}</span>
              <span>Requirements: {opp.requirements_status ?? 'not checked'}</span>
              <span>Deadline: {opp.deadline_status ?? 'unknown'}</span>
            </div>
          </div>

          {opp.official_url && (
            <a
              href={opp.official_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="flex items-center gap-1.5 text-xs text-teal-400 hover:text-teal-300 transition-colors"
            >
              <span>Official site</span>
              <ExternalLink size={11} />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
