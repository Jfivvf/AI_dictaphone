/**
 * Security Rules Verification Suite (Dirty Dozen Payloads)
 * Verifies all 12 adversarial payloads defined in security_spec.md
 * are rejected with PERMISSION_DENIED by firestore.rules.
 */

export interface DirtyDozenTestCase {
  id: number;
  name: string;
  operation: 'get' | 'list' | 'create' | 'update' | 'delete';
  path: string;
  auth: { uid: string; email_verified: boolean } | null;
  payload?: Record<string, unknown>;
  expectedResult: 'PERMISSION_DENIED';
}

export const DIRTY_DOZEN_TEST_CASES: DirtyDozenTestCase[] = [
  {
    id: 1,
    name: 'Identity Spoofing on Profile Creation',
    operation: 'create',
    path: '/users/victim_uid',
    auth: { uid: 'attacker_uid', email_verified: true },
    payload: {
      uid: 'victim_uid',
      name: 'Attacker',
      university: 'MSU',
      faculty: 'Math',
      group: '101',
      semester: 1,
      degree: 'Bachelor',
      theme: 'dark',
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 2,
    name: 'Shadow Field Injection on Profile Update',
    operation: 'update',
    path: '/users/user_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      uid: 'user_1',
      name: 'Alex',
      university: 'MSU',
      faculty: 'Math',
      group: '101',
      semester: 1,
      degree: 'Bachelor',
      theme: 'dark',
      isAdmin: true,
      createdAt: 'EXISTING_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 3,
    name: 'Unverified Email Write Attempt',
    operation: 'create',
    path: '/users/unverified_uid',
    auth: { uid: 'unverified_uid', email_verified: false },
    payload: {
      uid: 'unverified_uid',
      name: 'Alex',
      university: 'MSU',
      faculty: 'Math',
      group: '101',
      semester: 1,
      degree: 'Bachelor',
      theme: 'dark',
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 4,
    name: 'Cross-User PII Leak Read',
    operation: 'get',
    path: '/users/victim_uid/private/info',
    auth: { uid: 'attacker_uid', email_verified: true },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 5,
    name: 'Orphaned Lecture Creation Without Parent User Document',
    operation: 'create',
    path: '/users/no_profile_uid/lectures/lec_1',
    auth: { uid: 'no_profile_uid', email_verified: true },
    payload: {
      id: 'lec_1',
      ownerId: 'no_profile_uid',
      title: 'Calculus',
      subject: 'Math',
      lecturer: 'Prof',
      date: '2026-10-04',
      durationSeconds: 600,
      audioFileName: '',
      tags: ['Math'],
      noiseLevel: 'moderate',
      modelUsed: 'AI',
      quantization: 'Text',
      summaryMarkdown: '# Notes',
      transcriptText: 'Hello',
      formulasLatex: [],
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 6,
    name: 'Lecture OwnerId Mutation on Update',
    operation: 'update',
    path: '/users/user_1/lectures/lec_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      id: 'lec_1',
      ownerId: 'user_2',
      title: 'Calculus',
      subject: 'Math',
      lecturer: 'Prof',
      date: '2026-10-04',
      durationSeconds: 600,
      audioFileName: '',
      tags: ['Math'],
      noiseLevel: 'moderate',
      modelUsed: 'AI',
      quantization: 'Text',
      summaryMarkdown: '# Notes',
      transcriptText: 'Hello',
      formulasLatex: [],
      createdAt: 'EXISTING_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 7,
    name: 'Denial-of-Wallet Oversized String in Lecture Title',
    operation: 'create',
    path: '/users/user_1/lectures/lec_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      id: 'lec_1',
      ownerId: 'user_1',
      title: 'A'.repeat(5000),
      subject: 'Math',
      lecturer: 'Prof',
      date: '2026-10-04',
      durationSeconds: 600,
      audioFileName: '',
      tags: ['Math'],
      noiseLevel: 'moderate',
      modelUsed: 'AI',
      quantization: 'Text',
      summaryMarkdown: '# Notes',
      transcriptText: 'Hello',
      formulasLatex: [],
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 8,
    name: 'Unbounded Array Overflow on Lecture Tags',
    operation: 'create',
    path: '/users/user_1/lectures/lec_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      id: 'lec_1',
      ownerId: 'user_1',
      title: 'Calculus',
      subject: 'Math',
      lecturer: 'Prof',
      date: '2026-10-04',
      durationSeconds: 600,
      audioFileName: '',
      tags: Array.from({ length: 25 }, (_, i) => `tag_${i}`),
      noiseLevel: 'moderate',
      modelUsed: 'AI',
      quantization: 'Text',
      summaryMarkdown: '# Notes',
      transcriptText: 'Hello',
      formulasLatex: [],
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 9,
    name: 'Invalid Enum Value on Task Priority',
    operation: 'create',
    path: '/users/user_1/lectures/lec_1/tasks/task_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      id: 'task_1',
      lectureId: 'lec_1',
      ownerId: 'user_1',
      task: 'Solve problems',
      deadline: 'Friday',
      dateISO: '2026-10-10',
      type: 'homework',
      completed: false,
      priority: 'critical',
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 10,
    name: 'Orphaned Task Creation Without Parent Lecture',
    operation: 'create',
    path: '/users/user_1/lectures/nonexistent_lec/tasks/task_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      id: 'task_1',
      lectureId: 'nonexistent_lec',
      ownerId: 'user_1',
      task: 'Solve problems',
      deadline: 'Friday',
      dateISO: '2026-10-10',
      type: 'homework',
      completed: false,
      priority: 'high',
      createdAt: 'REQUEST_TIME',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 11,
    name: 'Forged Client Timestamp on Lecture Creation',
    operation: 'create',
    path: '/users/user_1/lectures/lec_1',
    auth: { uid: 'user_1', email_verified: true },
    payload: {
      id: 'lec_1',
      ownerId: 'user_1',
      title: 'Calculus',
      subject: 'Math',
      lecturer: 'Prof',
      date: '2026-10-04',
      durationSeconds: 600,
      audioFileName: '',
      tags: ['Math'],
      noiseLevel: 'moderate',
      modelUsed: 'AI',
      quantization: 'Text',
      summaryMarkdown: '# Notes',
      transcriptText: 'Hello',
      formulasLatex: [],
      createdAt: '2020-01-01T00:00:00Z',
      updatedAt: 'REQUEST_TIME'
    },
    expectedResult: 'PERMISSION_DENIED'
  },
  {
    id: 12,
    name: 'Unauthorized Cross-User Lecture List Scraping',
    operation: 'list',
    path: '/users/victim_uid/lectures',
    auth: { uid: 'attacker_uid', email_verified: true },
    expectedResult: 'PERMISSION_DENIED'
  }
];
