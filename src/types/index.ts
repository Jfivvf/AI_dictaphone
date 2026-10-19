export interface ActionItem {
  id: string;
  task: string;
  deadline: string;
  dateISO: string;
  type: 'homework' | 'exam' | 'reading' | 'project' | 'colloquium';
  completed: boolean;
  priority: 'high' | 'medium' | 'low';
}

export interface TranscriptSegment {
  id: string;
  startTime: number; // in seconds
  endTime: number;
  speaker: string;
  text: string;
  bookmarked?: boolean;
}

export interface LatexFormula {
  id: string;
  title: string;
  latex: string;
  context: string;
}

export interface SummaryRevision {
  id: string;
  timestamp: string;
  label: string;
  summaryMarkdown: string;
  wordCount: number;
}

export interface Lecture {
  id: string;
  title: string;
  subject: string;
  lecturer: string;
  date: string;
  durationSeconds: number;
  audioFileName?: string;
  tags: string[];
  noiseLevel: 'quiet' | 'moderate' | 'noisy' | 'echo';
  modelUsed: string;
  quantization: string;
  transcript: TranscriptSegment[];
  summaryMarkdown: string;
  summaryHistory?: SummaryRevision[];
  actionItems: ActionItem[];
  latexFormulas: LatexFormula[];
  keyDefinitions: { term: string; definition: string }[];
}

export interface AsrModelInfo {
  id: string;
  name: string;
  developer: string;
  architecture: string;
  huggingFaceId: string;
  parameters: string;
  werClean: number; // % Word Error Rate
  werNoisy: number; // % at 10 dB SNR
  werRussian: number; // % Russian specific
  rtfCpu: number; // Real Time Factor on CPU (lower = faster)
  rtfGpu: number; // Real Time Factor on GPU
  vramFp16: string;
  vramInt8: string;
  contextOrChunk: string;
  quantizationSupport: string[];
  bestUseFor: string;
  pros: string[];
  cons: string[];
}

export interface LlmModelInfo {
  id: string;
  name: string;
  developer: string;
  huggingFaceId: string;
  parameters: string;
  contextLength: string;
  ramQ4: string;
  russianQuality: number; // score 1-10
  mathLatexQuality: number; // score 1-10
  taskExtractionQuality: number; // score 1-10
  recommendedGguf: string;
  bestUseFor: string;
  description: string;
}

export interface StudentProfile {
  name: string;
  email: string;
  university: string;
  faculty: string;
  group: string;
  semester: number;
  degree: 'Bachelor' | 'Master' | 'Specialist';
  theme: 'dark' | 'light';
  avatarUrl?: string;
}

export interface AppSettings {
  asrModel: string;
  asrQuantization: 'fp16' | 'int8' | 'q5_0' | 'q4_0';
  llmModel: string;
  llmQuantization: 'q4_k_m' | 'q5_k_m' | 'q8_0' | 'fp16';
  contextWindowTokens: number;
  vadThreshold: number; // 0.1 to 0.9
  noiseSuppression: 'rnnoise' | 'spectral' | 'off';
  hardwareBackend: 'cuda' | 'metal' | 'cpu_avx512' | 'openvino';
  huggingFaceCacheDir: string;
  localStorageDbPath: string;
  audioSampleRate: number;
  offlineStrict: boolean;
  student: StudentProfile;
}
