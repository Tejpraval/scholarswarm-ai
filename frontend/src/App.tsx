import { Component, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { OnboardingPage } from './pages/OnboardingPage';
import { DashboardPage } from './pages/DashboardPage';
import { ResultsPage } from './pages/ResultsPage';
import type { WorkflowResults } from './types';

type AppState = 'onboarding' | 'dashboard' | 'results';
type SearchMode = 'demo' | 'live';

class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ScholarSwarm UI error:', error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
          <section className="max-w-lg rounded-2xl border border-slate-700 bg-slate-900 p-6 text-center">
            <h1 className="text-lg font-bold text-white">This page hit an error</h1>
            <p className="mt-2 text-sm text-slate-400">Your research run is saved. Reload the page to continue.</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-5 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-600"
            >
              Reload page
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [appState, setAppState] = useState<AppState>('onboarding');
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profileName, setProfileName] = useState<string>('Student');
  const [runId, setRunId] = useState<string | null>(null);
  const [results, setResults] = useState<WorkflowResults | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>('demo');

  const handleProfileReady = (id: string, mode: SearchMode) => {
    setProfileId(id);
    setSearchMode(mode);
    // Fetch the profile to get the name
    const apiBaseUrl = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api');
    fetch(`${apiBaseUrl}/profiles/${id}`)
      .then(r => r.json())
      .then(data => setProfileName(data.name || 'Student'))
      .catch(() => {});
    setAppState('dashboard');
  };

  const handleResultsReady = (res: WorkflowResults, rId: string) => {
    setResults(res);
    setRunId(rId);
    setAppState('results');
  };

  const handleBackToStart = () => {
    setAppState('onboarding');
    setProfileId(null);
    setRunId(null);
    setResults(null);
  };

  if (appState === 'onboarding') {
    return <OnboardingPage onProfileReady={handleProfileReady} />;
  }

  if (appState === 'dashboard' && profileId) {
    return (
      <DashboardPage
        profileId={profileId}
        profileName={profileName}
        mode={searchMode}
        onResultsReady={handleResultsReady}
      />
    );
  }

  if (appState === 'results' && results && runId) {
    return (
      <ResultsPage
        results={results}
        runId={runId}
        profileName={profileName}
        mode={searchMode}
        onBack={handleBackToStart}
      />
    );
  }

  // Fallback
  return <OnboardingPage onProfileReady={handleProfileReady} />;
}

export default function AppRoot() {
  return <AppErrorBoundary><App /></AppErrorBoundary>;
}
