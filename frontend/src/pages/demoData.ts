// This fictional profile is the only profile assessed by the curated fixture.
// The backend validates the qualifications and admission facts before loading it.

import type { ProfileCreateRequest } from '../types';

export const DEMO_PROFILE_DATA: ProfileCreateRequest = {
  name: 'Maya Iyer',
  email: 'maya.iyer@example.com',
  nationality: 'Indian',
  country_of_residence: 'India',
  degree_level: 'bachelors',
  degree_name: 'Bachelor of Computer Applications',
  institution: 'Fictional Demo University, India',
  cgpa: 8.6,
  cgpa_scale: 10.0,
  graduation_year: 2024,
  major: 'Computer Applications',
  skills: ['Python', 'SQL', 'Web development'],
  research_interests: [
    'Information Technology',
    'Software Systems'
  ],
  destination_preferences: ['Australia', 'New Zealand', 'Germany'],
  target_degree: 'masters',
  target_field: 'Information Technology and Computer Science',
  funding_preference: 'partial_funding',
  personal_statement_notes: (
    "FICTIONAL CURATED DEMO FACTS: international applicant; reports an unconditional offer for full-time CRICOS-registered coursework Master's study at the University of Sydney commencing Semester 1 2027; has not commenced that course; is not receiving an Australian Government scholarship. No IELTS/TOEFL score or DAAD language certificate is recorded. No University of Auckland offer is recorded. These are fictional facts for this demonstration profile, not facts about a real student."
  ),
};
