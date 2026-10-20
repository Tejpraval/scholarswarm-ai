import { useState, useRef } from 'react';
import {
  User, GraduationCap, MapPin, DollarSign, Github, Upload,
  CheckCircle, AlertCircle, ChevronRight, Sparkles, X, FileText
} from 'lucide-react';
import { createProfile, updateProfile, uploadDocument } from '../api/client';
import type { ProfileCreateRequest, DegreeLevel } from '../types';
import { DEMO_PROFILE_DATA } from './demoData';

interface Props {
  onProfileReady: (profileId: string, mode: 'demo' | 'live') => void;
}

const DESTINATIONS = ['Canada', 'Germany', 'Singapore', 'USA', 'UK', 'Australia', 'Netherlands', 'Sweden', 'Japan', 'South Korea'];
const SKILLS_SUGGESTIONS = ['Python', 'Machine Learning', 'TensorFlow', 'PyTorch', 'NLP', 'Computer Vision', 'Java', 'React', 'Node.js', 'SQL', 'C++', 'Data Science', 'Embedded Systems', 'VLSI', 'Robotics'];

export function OnboardingPage({ onProfileReady }: Props) {
  const [step, setStep] = useState(0); // 0: profile, 1: documents
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useDemo, setUseDemo] = useState(false);
  const [mode, setMode] = useState<'demo' | 'live'>('demo');
  const [profileId, setProfileId] = useState<string | null>(null);
  const [uploadedDocs, setUploadedDocs] = useState<{resume?: string; marksheet?: string}>({});
  const [skillInput, setSkillInput] = useState('');

  const resumeRef = useRef<HTMLInputElement>(null);
  const marksheetRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState<ProfileCreateRequest>({
    name: '',
    email: '',
    nationality: '',
    degree_level: 'bachelors',
    degree_name: '',
    institution: '',
    cgpa: undefined,
    cgpa_scale: 10.0,
    graduation_year: 2025,
    major: '',
    skills: [],
    research_interests: [],
    destination_preferences: [],
    target_degree: 'masters',
    target_field: '',
    funding_preference: 'full_funding',
    budget_usd_per_year: undefined,
    github_url: '',
    personal_statement_notes: '',
  });

  const loadDemo = () => {
    setForm(DEMO_PROFILE_DATA);
    setUseDemo(true);
  };

  const update = (field: keyof ProfileCreateRequest, value: unknown) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const addSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (trimmed && !(form.skills || []).includes(trimmed)) {
      update('skills', [...(form.skills || []), trimmed]);
    }
    setSkillInput('');
  };

  const removeSkill = (skill: string) => {
    update('skills', (form.skills || []).filter(s => s !== skill));
  };

  const toggleDestination = (dest: string) => {
    const prefs = form.destination_preferences || [];
    if (prefs.includes(dest)) {
      update('destination_preferences', prefs.filter(d => d !== dest));
    } else {
      update('destination_preferences', [...prefs, dest]);
    }
  };

  const handleSubmitProfile = async () => {
    if (!form.name.trim()) {
      setError('Name is required');
      return;
    }
    if ((form.destination_preferences || []).length === 0) {
      setError('Select at least one destination preference');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = profileId
        ? await updateProfile(profileId, form)
        : await createProfile(form);
      setProfileId(result.profile_id);
      setStep(1);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create profile');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (file: File, docType: 'resume' | 'marksheet') => {
    if (!profileId) return;
    if (file.type !== 'application/pdf') {
      setError('Only PDF files are accepted');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('File size must be under 10MB');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await uploadDocument(profileId, docType, file);
      setUploadedDocs(prev => ({ ...prev, [docType]: result.filename }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : `Failed to upload ${docType}`);
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = () => {
    if (profileId) {
      onProfileReady(profileId, mode);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-teal-500 to-blue-600 flex items-center justify-center">
              <Sparkles size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white leading-none">ScholarSwarm AI</h1>
              <p className="text-xs text-slate-500 leading-none mt-0.5">Multi-Agent Scholarship Discovery</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${step >= 0 ? 'bg-teal-400' : 'bg-slate-600'}`} />
            <div className={`w-8 h-0.5 ${step >= 1 ? 'bg-teal-400' : 'bg-slate-600'}`} />
            <div className={`w-2 h-2 rounded-full ${step >= 1 ? 'bg-teal-400' : 'bg-slate-600'}`} />
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-10">
        {step === 0 && (
          <div>
            <div className="mb-8">
              <h2 className="text-3xl font-bold text-white mb-2">Your Academic Profile</h2>
              <p className="text-slate-400">Choose a search mode, then enter the profile to assess.</p>
            </div>

            <section aria-label="Search mode" className="grid md:grid-cols-2 gap-3 mb-6">
              <button
                type="button"
                aria-pressed={mode === 'demo'}
                onClick={() => setMode('demo')}
                className={`rounded-xl border p-4 text-left transition-colors ${mode === 'demo' ? 'border-teal-500 bg-teal-950/30' : 'border-slate-700 bg-slate-900/40'}`}
              >
                <span className="block text-sm font-semibold text-teal-300">Demo Mode - curated data</span>
                <span className="block mt-1 text-xs text-slate-400">Prepared official-source examples; no Gemini or Tavily calls.</span>
              </button>
              <button
                type="button"
                aria-pressed={mode === 'live'}
                onClick={() => setMode('live')}
                className={`rounded-xl border p-4 text-left transition-colors ${mode === 'live' ? 'border-blue-500 bg-blue-950/30' : 'border-slate-700 bg-slate-900/40'}`}
              >
                <span className="block text-sm font-semibold text-blue-300">Live Research - AI agents</span>
                <span className="block mt-1 text-xs text-slate-400">Uses Tavily and Gemini. API failures stay visible; no demo fallback.</span>
              </button>
            </section>

            {/* Demo profile banner */}
            {!useDemo && (
              <button
                onClick={loadDemo}
                className="w-full mb-6 p-4 rounded-xl border border-teal-700/50 bg-teal-950/20 hover:bg-teal-950/30 transition-colors text-left flex items-center justify-between group"
              >
                <div>
                  <p className="text-sm font-semibold text-teal-300">Load curated fictional profile — Maya Iyer</p>
                  <p className="text-xs text-teal-600 mt-0.5">Bachelor's graduate · Australia / New Zealand / Germany · documented demo offer facts</p>
                </div>
                <ChevronRight size={16} className="text-teal-500 group-hover:translate-x-1 transition-transform" />
              </button>
            )}
            {useDemo && (
              <div className="mb-6 p-3 rounded-xl border border-teal-700/50 bg-teal-950/20 flex items-center gap-2">
                <CheckCircle size={14} className="text-teal-400" />
                <span className="text-sm text-teal-300">Fictional curated profile loaded — Maya Iyer</span>
                <button onClick={() => { setUseDemo(false); setForm({ name: '', skills: [], destination_preferences: [], funding_preference: 'full_funding', target_degree: 'masters', cgpa_scale: 10.0 }); }} className="ml-auto text-slate-500 hover:text-slate-300">
                  <X size={14} />
                </button>
              </div>
            )}

            {error && (
              <div className="mb-4 p-3 rounded-xl border border-red-700/50 bg-red-950/20 flex items-center gap-2">
                <AlertCircle size={14} className="text-red-400" />
                <span className="text-sm text-red-300">{error}</span>
              </div>
            )}

            <div className="space-y-6">
              {/* Personal Info */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <User size={16} className="text-teal-400" />
                  <h3 className="text-sm font-semibold text-slate-200">Personal Information</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2 sm:col-span-1">
                    <label className="block text-xs text-slate-400 mb-1.5">Full Name *</label>
                    <input
                      value={form.name}
                      onChange={e => update('name', e.target.value)}
                      placeholder="Your full name"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <label className="block text-xs text-slate-400 mb-1.5">Email</label>
                    <input
                      value={form.email || ''}
                      onChange={e => update('email', e.target.value)}
                      type="email"
                      placeholder="your@email.com"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Nationality</label>
                    <input
                      value={form.nationality || ''}
                      onChange={e => update('nationality', e.target.value)}
                      placeholder="e.g. Indian"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">GitHub Profile URL</label>
                    <div className="relative">
                      <Github size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                      <input
                        value={form.github_url || ''}
                        onChange={e => update('github_url', e.target.value)}
                        placeholder="https://github.com/username"
                        className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg pl-9 pr-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                      />
                    </div>
                  </div>
                </div>
              </section>

              {/* Academic Info */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <GraduationCap size={16} className="text-teal-400" />
                  <h3 className="text-sm font-semibold text-slate-200">Academic Background</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Current Degree</label>
                    <select
                      value={form.degree_level || ''}
                      onChange={e => update('degree_level', e.target.value)}
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-teal-600/60"
                    >
                      <option value="bachelors">Bachelor's</option>
                      <option value="masters">Master's</option>
                      <option value="phd">PhD</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Target Degree</label>
                    <select
                      value={form.target_degree || ''}
                      onChange={e => update('target_degree', e.target.value as DegreeLevel)}
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-teal-600/60"
                    >
                      <option value="masters">Master's</option>
                      <option value="phd">PhD</option>
                      <option value="bachelors">Bachelor's</option>
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-slate-400 mb-1.5">Degree Name</label>
                    <input
                      value={form.degree_name || ''}
                      onChange={e => update('degree_name', e.target.value)}
                      placeholder="e.g. B.Tech Computer Science"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-slate-400 mb-1.5">Institution</label>
                    <input
                      value={form.institution || ''}
                      onChange={e => update('institution', e.target.value)}
                      placeholder="University / College name"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">CGPA</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="10"
                      value={form.cgpa ?? ''}
                      onChange={e => update('cgpa', e.target.value ? parseFloat(e.target.value) : undefined)}
                      placeholder="e.g. 8.2"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">CGPA Scale</label>
                    <select
                      value={form.cgpa_scale || 10}
                      onChange={e => update('cgpa_scale', parseFloat(e.target.value))}
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-teal-600/60"
                    >
                      <option value={10}>Out of 10</option>
                      <option value={4}>Out of 4 (GPA)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Graduation Year</label>
                    <input
                      type="number"
                      min="2020"
                      max="2030"
                      value={form.graduation_year ?? ''}
                      onChange={e => update('graduation_year', e.target.value ? parseInt(e.target.value) : undefined)}
                      placeholder="2025"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Target Field</label>
                    <input
                      value={form.target_field || ''}
                      onChange={e => update('target_field', e.target.value)}
                      placeholder="e.g. AI / Machine Learning"
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 focus:ring-1 focus:ring-teal-600/30"
                    />
                  </div>
                </div>
              </section>

              {/* Skills */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Sparkles size={16} className="text-teal-400" />
                  <h3 className="text-sm font-semibold text-slate-200">Skills</h3>
                </div>
                <div className="flex gap-2 mb-3">
                  <input
                    value={skillInput}
                    onChange={e => setSkillInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSkill(skillInput); } }}
                    placeholder="Add a skill and press Enter"
                    className="flex-1 bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60"
                  />
                  <button
                    onClick={() => addSkill(skillInput)}
                    className="px-4 py-2 bg-teal-900/60 border border-teal-700/50 rounded-lg text-sm text-teal-300 hover:bg-teal-900/80 transition-colors"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2 mb-3">
                  {(form.skills || []).map(skill => (
                    <span key={skill} className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700/50 text-xs text-slate-300">
                      {skill}
                      <button onClick={() => removeSkill(skill)} className="text-slate-500 hover:text-slate-300">
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {SKILLS_SUGGESTIONS.filter(s => !(form.skills || []).includes(s)).slice(0, 8).map(skill => (
                    <button
                      key={skill}
                      onClick={() => addSkill(skill)}
                      className="px-2.5 py-1 rounded-full border border-slate-700/40 text-xs text-slate-500 hover:text-slate-300 hover:border-slate-600/60 transition-colors"
                    >
                      + {skill}
                    </button>
                  ))}
                </div>
              </section>

              {/* Destinations & Funding */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <MapPin size={16} className="text-teal-400" />
                  <h3 className="text-sm font-semibold text-slate-200">Destinations & Funding</h3>
                </div>
                <div className="mb-4">
                  <label className="block text-xs text-slate-400 mb-2">Preferred Study Destinations *</label>
                  <div className="flex flex-wrap gap-2">
                    {DESTINATIONS.map(dest => (
                      <button
                        key={dest}
                        onClick={() => toggleDestination(dest)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                          (form.destination_preferences || []).includes(dest)
                            ? 'bg-teal-900/70 border border-teal-600/60 text-teal-300'
                            : 'bg-slate-800/60 border border-slate-700/40 text-slate-500 hover:border-slate-600 hover:text-slate-400'
                        }`}
                      >
                        {dest}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Funding Preference</label>
                    <select
                      value={form.funding_preference || 'any'}
                      onChange={e => update('funding_preference', e.target.value)}
                      className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-teal-600/60"
                    >
                      <option value="full_funding">Full Funding Required</option>
                      <option value="partial_funding">Partial OK</option>
                      <option value="any">Any</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5">Annual Budget (USD, optional)</label>
                    <div className="relative">
                      <DollarSign size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                      <input
                        type="number"
                        value={form.budget_usd_per_year ?? ''}
                        onChange={e => update('budget_usd_per_year', e.target.value ? parseFloat(e.target.value) : undefined)}
                        placeholder="e.g. 5000"
                        className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg pl-9 pr-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60"
                      />
                    </div>
                  </div>
                </div>
              </section>

              {/* Notes */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-900/40 p-6">
                <label className="block text-xs text-slate-400 mb-1.5">Additional Notes (optional)</label>
                <textarea
                  value={form.personal_statement_notes || ''}
                  onChange={e => update('personal_statement_notes', e.target.value)}
                  placeholder="Any additional context for the agents — research goals, specific interests, circumstances..."
                  rows={3}
                  className="w-full bg-slate-800/80 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-teal-600/60 resize-none"
                />
              </section>
            </div>

            <button
              onClick={handleSubmitProfile}
              disabled={loading}
              className="w-full mt-6 py-3.5 rounded-xl bg-gradient-to-r from-teal-600 to-blue-600 text-white font-semibold text-sm hover:from-teal-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {profileId ? 'Saving profile changes...' : 'Creating profile...'}
                </>
              ) : (
                <>
                  {profileId ? 'Save Profile Changes' : 'Continue to Documents'}
                  <ChevronRight size={16} />
                </>
              )}
            </button>
          </div>
        )}

        {step === 1 && (
          <div>
            <div className="mb-8">
              <h2 className="text-3xl font-bold text-white mb-2">Upload Documents</h2>
              <p className="text-slate-400">Optionally upload your resume and marksheet to help the AI extract more information.</p>
            </div>

            <button
              type="button"
              onClick={() => { setError(null); setStep(0); }}
              className="mb-5 text-sm text-teal-300 hover:text-teal-200"
            >
              Edit profile
            </button>

            {error && (
              <div className="mb-4 p-3 rounded-xl border border-red-700/50 bg-red-950/20 flex items-center gap-2">
                <AlertCircle size={14} className="text-red-400" />
                <span className="text-sm text-red-300">{error}</span>
              </div>
            )}

            <div className="space-y-4 mb-8">
              {/* Resume upload */}
              <div
                onClick={() => resumeRef.current?.click()}
                className={`relative rounded-2xl border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
                  uploadedDocs.resume
                    ? 'border-teal-600/60 bg-teal-950/20'
                    : 'border-slate-700/60 hover:border-slate-600/80 bg-slate-900/30'
                }`}
              >
                <input
                  ref={resumeRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={e => e.target.files?.[0] && handleFileUpload(e.target.files[0], 'resume')}
                />
                {uploadedDocs.resume ? (
                  <div className="flex items-center justify-center gap-3">
                    <CheckCircle size={20} className="text-teal-400" />
                    <div className="text-left">
                      <p className="text-sm font-medium text-teal-300">Resume uploaded</p>
                      <p className="text-xs text-teal-600">{uploadedDocs.resume}</p>
                    </div>
                  </div>
                ) : (
                  <div>
                    <FileText size={28} className="mx-auto mb-2 text-slate-600" />
                    <p className="text-sm font-medium text-slate-300 mb-1">Upload Resume (PDF)</p>
                    <p className="text-xs text-slate-600">Click to browse · Max 10MB</p>
                  </div>
                )}
              </div>

              {/* Marksheet upload */}
              <div
                onClick={() => marksheetRef.current?.click()}
                className={`relative rounded-2xl border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
                  uploadedDocs.marksheet
                    ? 'border-teal-600/60 bg-teal-950/20'
                    : 'border-slate-700/60 hover:border-slate-600/80 bg-slate-900/30'
                }`}
              >
                <input
                  ref={marksheetRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={e => e.target.files?.[0] && handleFileUpload(e.target.files[0], 'marksheet')}
                />
                {uploadedDocs.marksheet ? (
                  <div className="flex items-center justify-center gap-3">
                    <CheckCircle size={20} className="text-teal-400" />
                    <div className="text-left">
                      <p className="text-sm font-medium text-teal-300">Marksheet uploaded</p>
                      <p className="text-xs text-teal-600">{uploadedDocs.marksheet}</p>
                    </div>
                  </div>
                ) : (
                  <div>
                    <Upload size={28} className="mx-auto mb-2 text-slate-600" />
                    <p className="text-sm font-medium text-slate-300 mb-1">Upload Marksheet (PDF)</p>
                    <p className="text-xs text-slate-600">Click to browse · Max 10MB</p>
                  </div>
                )}
              </div>
            </div>

            <button
              onClick={handleContinue}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-teal-600 to-blue-600 text-white font-semibold text-sm hover:from-teal-500 hover:to-blue-500 transition-all flex items-center justify-center gap-2"
            >
              Find My Scholarships
              <Sparkles size={16} />
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
