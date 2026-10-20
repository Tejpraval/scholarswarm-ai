import {
  CheckCircle, XCircle, Clock, Loader2, RefreshCw, SkipForward,
  Brain, Search, Shield, Target, Cpu
} from 'lucide-react';
import type { LucideProps } from 'lucide-react';
import type { AgentState } from '../stores/appStore';

type IconComponent = React.ForwardRefExoticComponent<Omit<LucideProps, 'ref'> & React.RefAttributes<SVGSVGElement>>;

interface Props {
  agent: AgentState;
  index: number;
}

const STATUS_CONFIG: Record<string, { icon: IconComponent; color: string; bg: string; border: string; label: string }> = {
  pending: {
    icon: Clock,
    color: 'text-slate-500',
    bg: 'bg-slate-800/50',
    border: 'border-slate-700/50',
    label: 'Pending',
  },
  running: {
    icon: Loader2,
    color: 'text-blue-400',
    bg: 'bg-blue-950/30',
    border: 'border-blue-800/50',
    label: 'Running',
  },
  completed: {
    icon: CheckCircle,
    color: 'text-teal-400',
    bg: 'bg-teal-950/20',
    border: 'border-teal-800/50',
    label: 'Done',
  },
  failed: {
    icon: XCircle,
    color: 'text-red-400',
    bg: 'bg-red-950/20',
    border: 'border-red-800/50',
    label: 'Failed',
  },
  retrying: {
    icon: RefreshCw,
    color: 'text-yellow-400',
    bg: 'bg-yellow-950/20',
    border: 'border-yellow-800/50',
    label: 'Retrying',
  },
  skipped: {
    icon: SkipForward,
    color: 'text-slate-500',
    bg: 'bg-slate-800/30',
    border: 'border-slate-700/30',
    label: 'Skipped',
  },
};

const AGENT_ICONS: Record<string, IconComponent> = {
  student_profiler: Brain,
  scholarship_researcher: Search,
  eligibility_verifier: Shield,
  matching_agent: Target,
  orchestrator: Cpu,
  output_validator: CheckCircle,
};

export function AgentStatusCard({ agent, index }: Props) {
  const config = STATUS_CONFIG[agent.status] || STATUS_CONFIG.pending;
  const StatusIcon = config.icon;
  const AgentIcon = (AGENT_ICONS[agent.name] || Cpu) as IconComponent;
  const isRunning = agent.status === 'running';
  const isRetrying = agent.status === 'retrying';

  return (
    <div
      className={`relative rounded-xl border p-4 transition-all duration-300 ${config.bg} ${config.border}`}
    >
      {/* Status indicator dot */}
      <div className="flex items-start gap-3">
        <div className="relative flex-shrink-0 mt-0.5">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
            isRunning ? 'bg-blue-900/60' : 'bg-slate-800/80'
          }`}>
            <AgentIcon size={18} className={config.color} />
          </div>
          {isRunning && (
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-blue-400 rounded-full animate-ping" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-sm font-semibold text-slate-200">{agent.label}</h4>
            <div className={`flex items-center gap-1 text-xs font-medium ${config.color}`}>
              <StatusIcon
                size={12}
                className={isRunning || isRetrying ? 'animate-spin' : ''}
              />
              <span>{config.label}</span>
              {agent.retryCount > 0 && (
                <span className="text-yellow-400 ml-1">×{agent.retryCount}</span>
              )}
            </div>
          </div>

          <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
            {agent.lastMessage}
          </p>

          {agent.durationMs && agent.status === 'completed' && (
            <div className="mt-1.5 text-xs text-slate-600">
              {(agent.durationMs / 1000).toFixed(1)}s
            </div>
          )}
        </div>
      </div>

      {/* Progress line connector */}
      {index < 3 && (
        <div className={`absolute left-[28px] bottom-0 translate-y-full w-0.5 h-4 ${
          agent.status === 'completed' ? 'bg-teal-700' : 'bg-slate-700'
        }`} />
      )}
    </div>
  );
}
