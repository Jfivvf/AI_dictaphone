import { initializeApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut as firebaseSignOut,
  User as FirebaseUser
} from 'firebase/auth';
import {
  initializeFirestore,
  setLogLevel,
  doc,
  getDoc,
  getDocs,
  setDoc,
  updateDoc,
  deleteDoc,
  collection,
  query,
  where,
  writeBatch,
  serverTimestamp,
} from 'firebase/firestore';
import firebaseConfig from '../firebase-applet-config.json';
import { Lecture, ActionItem, StudentProfile, TranscriptSegment, LatexFormula } from './types';

// Suppress internal @firebase/firestore WebChannel transport retry noise in proxy/iframe networks
setLogLevel('silent');

// Initialize Firebase App, Firestore (with HTTP Long-Polling for reliable proxy/ISP connectivity), and Auth
const app = initializeApp(firebaseConfig);
export const db = initializeFirestore(
  app,
  { experimentalForceLongPolling: true },
  firebaseConfig.firestoreDatabaseId
);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();

// ============================================================================
// Standardized Firestore Error Handler
// ============================================================================
export enum OperationType {
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  LIST = 'list',
  GET = 'get',
  WRITE = 'write',
}

export interface FirestoreErrorInfo {
  error: string;
  operationType: OperationType;
  path: string | null;
  authInfo: {
    userId?: string | null;
    email?: string | null;
    emailVerified?: boolean | null;
    isAnonymous?: boolean | null;
    tenantId?: string | null;
    providerInfo?: {
      providerId?: string | null;
      email?: string | null;
    }[];
  };
}

export function handleFirestoreError(
  error: unknown,
  operationType: OperationType,
  path: string | null
): never {
  const errInfo: FirestoreErrorInfo = {
    error: error instanceof Error ? error.message : String(error),
    authInfo: {
      userId: auth.currentUser?.uid,
      email: auth.currentUser?.email,
      emailVerified: auth.currentUser?.emailVerified,
      isAnonymous: auth.currentUser?.isAnonymous,
      tenantId: auth.currentUser?.tenantId,
      providerInfo:
        auth.currentUser?.providerData?.map((provider) => ({
          providerId: provider.providerId,
          email: provider.email,
        })) || [],
    },
    operationType,
    path,
  };
  console.error('Firestore Error: ', JSON.stringify(errInfo));
  throw new Error(JSON.stringify(errInfo));
}

// ============================================================================
// Defensive Sanitization & Schema Boundary Helpers (Synced with Blueprint)
// ============================================================================
const ID_REGEX = /^[a-zA-Z0-9_\-]+$/;

export function sanitizeId(rawId: string, fallbackPrefix = 'item'): string {
  const cleaned = rawId.replace(/[^a-zA-Z0-9_\-]/g, '_').slice(0, 128);
  if (!cleaned || !ID_REGEX.test(cleaned)) {
    return `${fallbackPrefix}_${Date.now()}`;
  }
  return cleaned;
}

function clampString(val: string | undefined | null, minLen: number, maxLen: number, fallback: string): string {
  const str = (val ?? '').trim();
  const nonEmpty = str.length >= minLen ? str : fallback;
  return nonEmpty.slice(0, maxLen);
}

// Serialize/Deserialize transcript segments into human-readable text lines
function serializeTranscript(segments: TranscriptSegment[]): string {
  if (!segments || segments.length === 0) {
    return '[00:00] Лектор: Запись сохранена.';
  }
  const lines = segments.map((s) => {
    const start = Math.max(0, Math.floor(s.startTime || 0));
    const end = Math.max(start, Math.floor(s.endTime || start + 5));
    const speaker = (s.speaker || 'Лектор').replace(/\|/g, ' ').trim();
    const text = (s.text || '').replace(/\r?\n/g, ' ').trim();
    const bm = s.bookmarked ? '1' : '0';
    return `${start}|${end}|${bm}|${speaker}|${text}`;
  });
  return clampString(lines.join('\n'), 1, 100000, '0|5|0|Лектор|Запись сохранена.');
}

function deserializeTranscript(transcriptText: string, lectureId: string): TranscriptSegment[] {
  if (!transcriptText) {
    return [
      {
        id: `seg_${lectureId}_0`,
        startTime: 0,
        endTime: 5,
        speaker: 'Лектор',
        text: 'Запись сохранена.',
        bookmarked: false,
      },
    ];
  }
  const lines = transcriptText.split('\n').filter((l) => l.trim().length > 0);
  return lines.map((line, idx) => {
    const parts = line.split('|');
    if (parts.length >= 5) {
      const startTime = Number(parts[0]) || 0;
      const endTime = Number(parts[1]) || startTime + 5;
      const bookmarked = parts[2] === '1';
      const speaker = parts[3] || 'Лектор';
      const text = parts.slice(4).join('|') || '...';
      return {
        id: `seg_${lectureId}_${idx}`,
        startTime,
        endTime,
        speaker,
        text,
        bookmarked,
      };
    }
    return {
      id: `seg_${lectureId}_${idx}`,
      startTime: idx * 10,
      endTime: (idx + 1) * 10,
      speaker: 'Лектор',
      text: line,
      bookmarked: false,
    };
  });
}

function serializeFormulas(formulas: LatexFormula[]): string[] {
  if (!formulas || formulas.length === 0) return [];
  return formulas.slice(0, 20).map((f) => {
    const title = clampString(f.title, 1, 150, 'Формула').replace(/\|/g, ' ');
    const latex = clampString(f.latex, 1, 500, 'x = y').replace(/\|/g, ' ');
    const context = clampString(f.context, 1, 300, 'Из лекции').replace(/\|/g, ' ');
    return `${title}|${latex}|${context}`.slice(0, 1000);
  });
}

function deserializeFormulas(rawList: unknown, lectureId: string): LatexFormula[] {
  if (!Array.isArray(rawList)) return [];
  return rawList
    .filter((item): item is string => typeof item === 'string' && item.length > 0)
    .map((entry, idx) => {
      const parts = entry.split('|');
      if (parts.length >= 3) {
        return {
          id: `f_${lectureId}_${idx}`,
          title: parts[0] || 'Формула',
          latex: parts[1] || '',
          context: parts.slice(2).join('|') || '',
        };
      }
      return {
        id: `f_${lectureId}_${idx}`,
        title: 'Формула из конспекта',
        latex: entry,
        context: 'Извлечено из лекции',
      };
    });
}

// ============================================================================
// Database Operations for User Profile & Private Info
// ============================================================================
export async function ensureUserProfileInFirestore(
  user: FirebaseUser,
  defaultStudent: StudentProfile
): Promise<StudentProfile> {
  const uid = sanitizeId(user.uid, 'user');
  const userDocRef = doc(db, 'users', uid);
  const privateDocRef = doc(db, 'users', uid, 'private', 'info');

  try {
    const snap = await getDoc(userDocRef);
    let email = user.email || defaultStudent.email || 'student@university.ru';

    if (snap.exists()) {
      const data = snap.data();
      try {
        const privSnap = await getDoc(privateDocRef);
        if (privSnap.exists() && typeof privSnap.data().email === 'string') {
          email = privSnap.data().email;
        }
      } catch {
        // Ignore if private info doc wasn't created yet
      }
      return {
        name: data.name || user.displayName || defaultStudent.name,
        email,
        university: data.university || defaultStudent.university,
        faculty: data.faculty || defaultStudent.faculty,
        group: data.group || defaultStudent.group,
        semester: typeof data.semester === 'number' ? data.semester : defaultStudent.semester,
        degree:
          data.degree === 'Bachelor' || data.degree === 'Master' || data.degree === 'Specialist'
            ? data.degree
            : 'Bachelor',
        theme: data.theme === 'light' ? 'light' : 'dark',
      };
    }

    // Create both UserProfile and UserPrivateInfo atomically in a batch
    const newProfile: StudentProfile = {
      name: clampString(user.displayName || defaultStudent.name, 1, 150, 'Студент'),
      email: clampString(user.email || defaultStudent.email, 3, 254, 'student@university.ru'),
      university: clampString(defaultStudent.university, 1, 200, 'Университет'),
      faculty: clampString(defaultStudent.faculty, 1, 200, 'Факультет'),
      group: clampString(defaultStudent.group, 1, 50, '101-А'),
      semester: Math.min(12, Math.max(1, Math.round(defaultStudent.semester || 1))),
      degree:
        defaultStudent.degree === 'Bachelor' ||
        defaultStudent.degree === 'Master' ||
        defaultStudent.degree === 'Specialist'
          ? defaultStudent.degree
          : 'Bachelor',
      theme: defaultStudent.theme === 'light' ? 'light' : 'dark',
    };

    const batch = writeBatch(db);
    batch.set(userDocRef, {
      uid,
      name: newProfile.name,
      university: newProfile.university,
      faculty: newProfile.faculty,
      group: newProfile.group,
      semester: newProfile.semester,
      degree: newProfile.degree,
      theme: newProfile.theme,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    });

    batch.set(privateDocRef, {
      uid,
      email: newProfile.email,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    });

    await batch.commit();
    return newProfile;
  } catch (error: any) {
    const msg = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();
    if (msg.includes('offline') || msg.includes('unavailable') || error?.code === 'unavailable') {
      return {
        ...defaultStudent,
        name: user.displayName || defaultStudent.name,
        email: user.email || defaultStudent.email,
      };
    }
    handleFirestoreError(error, OperationType.WRITE, `/users/${uid}`);
  }
}

export async function updateUserProfileInFirestore(
  uid: string,
  profile: StudentProfile
): Promise<void> {
  const safeUid = sanitizeId(uid, 'user');
  const userDocRef = doc(db, 'users', safeUid);
  const privateDocRef = doc(db, 'users', safeUid, 'private', 'info');

  try {
    await updateDoc(userDocRef, {
      name: clampString(profile.name, 1, 150, 'Студент'),
      university: clampString(profile.university, 1, 200, 'Университет'),
      faculty: clampString(profile.faculty, 1, 200, 'Факультет'),
      group: clampString(profile.group, 1, 50, '101-А'),
      semester: Math.min(12, Math.max(1, Math.round(profile.semester || 1))),
      degree:
        profile.degree === 'Bachelor' || profile.degree === 'Master' || profile.degree === 'Specialist'
          ? profile.degree
          : 'Bachelor',
      theme: profile.theme === 'light' ? 'light' : 'dark',
      updatedAt: serverTimestamp(),
    });

    const safeEmail = clampString(profile.email, 3, 254, 'student@university.ru');
    const privSnap = await getDoc(privateDocRef);
    if (privSnap.exists()) {
      await updateDoc(privateDocRef, {
        email: safeEmail,
        updatedAt: serverTimestamp(),
      });
    } else {
      await setDoc(privateDocRef, {
        uid: safeUid,
        email: safeEmail,
        createdAt: serverTimestamp(),
        updatedAt: serverTimestamp(),
      });
    }
  } catch (error) {
    handleFirestoreError(error, OperationType.UPDATE, `/users/${safeUid}`);
  }
}

// ============================================================================
// Database Operations for Lectures & Tasks
// ============================================================================
export function buildLectureFirestorePayload(uid: string, lecture: Lecture) {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lecture.id, 'lec');
  const rawTags = Array.isArray(lecture.tags) && lecture.tags.length > 0 ? lecture.tags : [lecture.subject || 'Лекция'];
  const safeTags = rawTags
    .slice(0, 10)
    .map((t) => clampString(t, 1, 100, 'Лекция'));

  const validNoise =
    lecture.noiseLevel === 'quiet' ||
    lecture.noiseLevel === 'moderate' ||
    lecture.noiseLevel === 'noisy' ||
    lecture.noiseLevel === 'echo'
      ? lecture.noiseLevel
      : 'moderate';

  return {
    id: safeLectureId,
    ownerId: safeUid,
    title: clampString(lecture.title, 1, 300, 'Запись лекции'),
    subject: clampString(lecture.subject, 1, 200, 'Учебное занятие'),
    lecturer: clampString(lecture.lecturer, 1, 200, 'Преподаватель'),
    date: clampString(lecture.date, 1, 100, new Date().toLocaleDateString('ru-RU')),
    durationSeconds: Math.min(86400, Math.max(0, Math.round(lecture.durationSeconds || 60))),
    audioFileName: (lecture.audioFileName || '').slice(0, 255),
    tags: safeTags,
    noiseLevel: validNoise,
    modelUsed: clampString(lecture.modelUsed, 1, 200, 'Нейросеть распознавания речи'),
    quantization: clampString(lecture.quantization, 1, 100, 'Текст'),
    summaryMarkdown: clampString(lecture.summaryMarkdown, 1, 100000, '## Конспект лекции'),
    transcriptText: serializeTranscript(lecture.transcript),
    formulasLatex: serializeFormulas(lecture.latexFormulas),
  };
}

export function buildTaskFirestorePayload(uid: string, lectureId: string, item: ActionItem) {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lectureId, 'lec');
  const safeTaskId = sanitizeId(item.id, 'task');

  const validType =
    item.type === 'homework' ||
    item.type === 'exam' ||
    item.type === 'reading' ||
    item.type === 'project' ||
    item.type === 'colloquium'
      ? item.type
      : 'homework';

  const validPriority =
    item.priority === 'high' || item.priority === 'medium' || item.priority === 'low'
      ? item.priority
      : 'medium';

  return {
    id: safeTaskId,
    lectureId: safeLectureId,
    ownerId: safeUid,
    task: clampString(item.task, 1, 1000, 'Повторить материал лекции'),
    deadline: clampString(item.deadline, 1, 200, 'К следующему занятию'),
    dateISO: clampString(item.dateISO, 1, 40, new Date().toISOString().split('T')[0]),
    type: validType,
    completed: Boolean(item.completed),
    priority: validPriority,
  };
}

export async function createLectureInFirestore(uid: string, lecture: Lecture): Promise<Lecture> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lecture.id, 'lec');
  const lectureRef = doc(db, 'users', safeUid, 'lectures', safeLectureId);
  const payload = buildLectureFirestorePayload(safeUid, { ...lecture, id: safeLectureId });

  try {
    await setDoc(lectureRef, {
      ...payload,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    });

    // Save tasks in subcollection after parent lecture document exists
    const sanitizedTasks: ActionItem[] = [];
    for (const item of lecture.actionItems || []) {
      const taskPayload = buildTaskFirestorePayload(safeUid, safeLectureId, item);
      const taskRef = doc(db, 'users', safeUid, 'lectures', safeLectureId, 'tasks', taskPayload.id);
      await setDoc(taskRef, {
        ...taskPayload,
        createdAt: serverTimestamp(),
        updatedAt: serverTimestamp(),
      });
      sanitizedTasks.push({
        id: taskPayload.id,
        task: taskPayload.task,
        deadline: taskPayload.deadline,
        dateISO: taskPayload.dateISO,
        type: taskPayload.type,
        completed: taskPayload.completed,
        priority: taskPayload.priority,
      });
    }

    return {
      ...lecture,
      id: safeLectureId,
      actionItems: sanitizedTasks,
    };
  } catch (error) {
    handleFirestoreError(error, OperationType.CREATE, `/users/${safeUid}/lectures/${safeLectureId}`);
  }
}

export async function updateLectureInFirestore(uid: string, lecture: Lecture): Promise<void> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lecture.id, 'lec');
  const lectureRef = doc(db, 'users', safeUid, 'lectures', safeLectureId);
  const payload = buildLectureFirestorePayload(safeUid, lecture);

  try {
    await updateDoc(lectureRef, {
      title: payload.title,
      subject: payload.subject,
      lecturer: payload.lecturer,
      audioFileName: payload.audioFileName,
      tags: payload.tags,
      summaryMarkdown: payload.summaryMarkdown,
      transcriptText: payload.transcriptText,
      formulasLatex: payload.formulasLatex,
      updatedAt: serverTimestamp(),
    });
  } catch (error) {
    handleFirestoreError(error, OperationType.UPDATE, `/users/${safeUid}/lectures/${safeLectureId}`);
  }
}

export async function deleteLectureFromFirestore(uid: string, lectureId: string): Promise<void> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lectureId, 'lec');
  const tasksCol = collection(db, 'users', safeUid, 'lectures', safeLectureId, 'tasks');
  const tasksQuery = query(
    tasksCol,
    where('ownerId', '==', safeUid),
    where('lectureId', '==', safeLectureId)
  );

  try {
    // Delete child tasks first while parent lecture still exists
    const tasksSnap = await getDocs(tasksQuery);
    for (const taskDoc of tasksSnap.docs) {
      await deleteDoc(taskDoc.ref);
    }
    const lectureRef = doc(db, 'users', safeUid, 'lectures', safeLectureId);
    await deleteDoc(lectureRef);
  } catch (error) {
    handleFirestoreError(error, OperationType.DELETE, `/users/${safeUid}/lectures/${safeLectureId}`);
  }
}

export async function toggleTaskInFirestore(
  uid: string,
  lectureId: string,
  taskId: string,
  completed: boolean
): Promise<void> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lectureId, 'lec');
  const safeTaskId = sanitizeId(taskId, 'task');
  const taskRef = doc(db, 'users', safeUid, 'lectures', safeLectureId, 'tasks', safeTaskId);

  try {
    await updateDoc(taskRef, {
      completed: Boolean(completed),
      updatedAt: serverTimestamp(),
    });
  } catch (error) {
    handleFirestoreError(
      error,
      OperationType.UPDATE,
      `/users/${safeUid}/lectures/${safeLectureId}/tasks/${safeTaskId}`
    );
  }
}

export async function updateTaskPriorityInFirestore(
  uid: string,
  lectureId: string,
  taskId: string,
  priority: 'high' | 'medium' | 'low'
): Promise<void> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lectureId, 'lec');
  const safeTaskId = sanitizeId(taskId, 'task');
  const taskRef = doc(db, 'users', safeUid, 'lectures', safeLectureId, 'tasks', safeTaskId);
  const safePriority: 'high' | 'medium' | 'low' =
    priority === 'high' || priority === 'medium' || priority === 'low' ? priority : 'medium';

  try {
    await updateDoc(taskRef, {
      priority: safePriority,
      updatedAt: serverTimestamp(),
    });
  } catch (error) {
    handleFirestoreError(
      error,
      OperationType.UPDATE,
      `/users/${safeUid}/lectures/${safeLectureId}/tasks/${safeTaskId}`
    );
  }
}

export async function addTaskToFirestore(
  uid: string,
  lectureId: string,
  task: ActionItem
): Promise<ActionItem> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lectureId, 'lec');
  const payload = buildTaskFirestorePayload(safeUid, safeLectureId, task);
  const taskRef = doc(db, 'users', safeUid, 'lectures', safeLectureId, 'tasks', payload.id);

  try {
    await setDoc(taskRef, {
      ...payload,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    });
    return {
      id: payload.id,
      task: payload.task,
      deadline: payload.deadline,
      dateISO: payload.dateISO,
      type: payload.type,
      completed: payload.completed,
      priority: payload.priority,
    };
  } catch (error) {
    handleFirestoreError(
      error,
      OperationType.CREATE,
      `/users/${safeUid}/lectures/${safeLectureId}/tasks/${payload.id}`
    );
  }
}

export async function loadTasksForLecture(uid: string, lectureId: string): Promise<ActionItem[]> {
  const safeUid = sanitizeId(uid, 'user');
  const safeLectureId = sanitizeId(lectureId, 'lec');
  const tasksCol = collection(db, 'users', safeUid, 'lectures', safeLectureId, 'tasks');
  const q = query(tasksCol, where('ownerId', '==', safeUid), where('lectureId', '==', safeLectureId));

  try {
    const snap = await getDocs(q);
    return snap.docs.map((d) => {
      const data = d.data();
      return {
        id: data.id || d.id,
        task: data.task || '',
        deadline: data.deadline || '',
        dateISO: data.dateISO || '',
        type: data.type || 'homework',
        completed: Boolean(data.completed),
        priority: data.priority || 'medium',
      };
    });
  } catch (error) {
    handleFirestoreError(error, OperationType.LIST, `/users/${safeUid}/lectures/${safeLectureId}/tasks`);
  }
}

export function mapDocToLecture(docId: string, data: Record<string, any>, tasks: ActionItem[]): Lecture {
  const lectureId = data.id || docId;
  return {
    id: lectureId,
    title: data.title || 'Запись лекции',
    subject: data.subject || 'Учебное занятие',
    lecturer: data.lecturer || 'Преподаватель',
    date: data.date || '',
    durationSeconds: typeof data.durationSeconds === 'number' ? data.durationSeconds : 60,
    audioFileName: data.audioFileName ? data.audioFileName : undefined,
    tags: Array.isArray(data.tags) ? data.tags : [],
    noiseLevel: data.noiseLevel || 'moderate',
    modelUsed: data.modelUsed || 'Нейросеть распознавания речи',
    quantization: data.quantization || 'Текст',
    summaryMarkdown: data.summaryMarkdown || '',
    transcript: deserializeTranscript(data.transcriptText || '', lectureId),
    latexFormulas: deserializeFormulas(data.formulasLatex, lectureId),
    actionItems: tasks,
    keyDefinitions: [],
  };
}

export async function signInWithGooglePopup(): Promise<FirebaseUser> {
  const result = await signInWithPopup(auth, googleProvider);
  return result.user;
}

export async function signOutUser(): Promise<void> {
  await firebaseSignOut(auth);
}
