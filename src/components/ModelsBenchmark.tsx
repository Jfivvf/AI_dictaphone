import React, { useState } from 'react';
import { 
  Cpu, 
  Sparkles, 
  HelpCircle, 
  Sliders, 
  ExternalLink, 
  CheckCircle2, 
  XCircle, 
  Zap, 
  BookOpen, 
  Layers, 
  Clock, 
  HardDrive
} from 'lucide-react';
import { 
  TOP_5_ASR_MODELS, 
  TOP_5_LLM_MODELS, 
  QUANTIZATION_GUIDE, 
  CONTEXT_LENGTH_GUIDE, 
  HUGGINGFACE_GUIDE, 
  HABR_ARTICLE_ANALYSIS 
} from '../data/modelsBenchmark';

export const ModelsBenchmark: React.FC = () => {
  const [activeSection, setActiveSection] = useState<'asr' | 'llm' | 'simulator' | 'guide'>('asr');
  
  // Simulator state
  const [simNoiseSnr, setSimNoiseSnr] = useState<number>(15); // dB
  const [simHardware, setSimHardware] = useState<'cpu' | 'gpu_mid' | 'gpu_high' | 'apple_silicon'>('gpu_mid');
  const [simLectureLengthMin, setSimLectureLengthMin] = useState<number>(80);

  // Compute simulation stats for 80-min lecture
  const getSimResults = () => {
    // Noise penalty
    const noiseFactor = simNoiseSnr < 10 ? 1.6 : simNoiseSnr < 20 ? 1.2 : 1.0;
    
    // Hardware speed factor
    const speedFactor = 
      simHardware === 'cpu' ? 0.25 : 
      simHardware === 'apple_silicon' ? 0.08 : 
      simHardware === 'gpu_high' ? 0.03 : 0.05;

    const fwWer = Math.min(28, +(5.4 * noiseFactor).toFixed(1));
    const gigaWer = Math.min(25, +(4.2 * noiseFactor * 0.95).toFixed(1));
    const cppWer = Math.min(32, +(6.8 * noiseFactor * 1.1).toFixed(1));

    const totalSeconds = simLectureLengthMin * 60;
    const processTimeMinutes = Math.max(1, Math.round((totalSeconds * speedFactor) / 60));

    return { fwWer, gigaWer, cppWer, processTimeMinutes };
  };

  const simResults = getSimResults();

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-neutral-950">
      <div className="max-w-5xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800/60">
                AI Research & Benchmarks
              </span>
              <span className="text-xs text-neutral-500">Автономные локальные модели</span>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight mt-1">
              Анализ топ-5 нейросетей и теоретическое сравнение
            </h1>
            <p className="text-xs text-neutral-400 mt-0.5">
              Подбор моделей ASR и LLM для студенческого диктофона, анализ зашумленности и квантования
            </p>
          </div>

          {/* Section Tabs */}
          <div className="flex items-center gap-1 p-1 bg-neutral-900 border border-neutral-800 rounded-lg overflow-x-auto">
            <button
              onClick={() => setActiveSection('asr')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                activeSection === 'asr'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Топ-5 ASR (Речь)
            </button>

            <button
              onClick={() => setActiveSection('llm')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                activeSection === 'llm'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Топ-5 LLM (Конспект)
            </button>

            <button
              onClick={() => setActiveSection('simulator')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                activeSection === 'simulator'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Симулятор шума
            </button>

            <button
              onClick={() => setActiveSection('guide')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-colors ${
                activeSection === 'guide'
                  ? 'bg-neutral-800 text-white'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Ликбез: Квантование & Хабр
            </button>
          </div>
        </div>

        {/* SECTION 1: TOP-5 ASR SPEECH MODELS */}
        {activeSection === 'asr' && (
          <div className="space-y-6">
            <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-800/40 flex items-start gap-3">
              <Zap className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
              <div className="text-xs text-neutral-300 leading-relaxed">
                <span className="font-semibold text-white">Вывод для команды: </span>
                Для академических лекций на русском языке лучшим выбором является комбинация{' '}
                <strong className="text-indigo-300">Silero VAD (фильтрация пауз)</strong> +{' '}
                <strong className="text-indigo-300">Faster-Whisper Large-v3-Turbo в INT8</strong> или{' '}
                <strong className="text-indigo-300">GigaAM v2</strong>. Они обеспечивают рекордно низкий уровень ошибок (WER ~4.2 - 5.4%) и полностью помещаются в 2 ГБ видеопамяти ноутбука.
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4">
              {TOP_5_ASR_MODELS.map((model, idx) => (
                <div
                  key={model.id}
                  className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-neutral-800 text-neutral-300 text-xs font-bold flex items-center justify-center font-mono">
                        {idx + 1}
                      </span>
                      <div>
                        <h3 className="text-sm font-bold text-white">
                          {model.name}
                        </h3>
                        <div className="text-[11px] text-neutral-400">
                          {model.developer} · {model.architecture}
                        </div>
                      </div>
                    </div>

                    <a
                      href={`https://huggingface.co/${model.huggingFaceId}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 bg-neutral-950 px-2.5 py-1 rounded border border-neutral-800 self-start sm:self-center"
                    >
                      <span>HF: {model.huggingFaceId}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>

                  {/* Metrics Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Ошибки (Чистый звук)</div>
                      <div className="font-mono text-sm font-bold text-emerald-400 mt-0.5">
                        WER {model.werClean}%
                      </div>
                      <div className="text-[10px] text-neutral-400">Русский язык: {model.werRussian}%</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Шум (10 dB SNR)</div>
                      <div className="font-mono text-sm font-bold text-amber-400 mt-0.5">
                        WER {model.werNoisy}%
                      </div>
                      <div className="text-[10px] text-neutral-400">Задние парты лектория</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Скорость (RTF)</div>
                      <div className="font-mono text-sm font-bold text-indigo-300 mt-0.5">
                        GPU: {model.rtfGpu} / CPU: {model.rtfCpu}
                      </div>
                      <div className="text-[10px] text-neutral-400">Параметров: {model.parameters}</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Память VRAM (INT8)</div>
                      <div className="font-mono text-sm font-bold text-white mt-0.5">
                        {model.vramInt8}
                      </div>
                      <div className="text-[10px] text-neutral-400">FP16: {model.vramFp16}</div>
                    </div>
                  </div>

                  {/* Best use */}
                  <div className="text-xs text-neutral-300">
                    <strong className="text-neutral-200">Рекомендуемый сценарий: </strong>
                    {model.bestUseFor}
                  </div>

                  {/* Pros and Cons */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
                    <div className="space-y-1">
                      <div className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Преимущества
                      </div>
                      {model.pros.map((pro, pIdx) => (
                        <div key={pIdx} className="text-neutral-300 pl-4 relative text-[11px] leading-tight">
                          <span className="absolute left-1 text-neutral-500">•</span>
                          {pro}
                        </div>
                      ))}
                    </div>

                    <div className="space-y-1">
                      <div className="text-[11px] font-semibold text-rose-400 flex items-center gap-1">
                        <XCircle className="w-3.5 h-3.5" /> Ограничения
                      </div>
                      {model.cons.map((con, cIdx) => (
                        <div key={cIdx} className="text-neutral-400 pl-4 relative text-[11px] leading-tight">
                          <span className="absolute left-1 text-neutral-500">•</span>
                          {con}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SECTION 2: TOP-5 LOCAL LLMS */}
        {activeSection === 'llm' && (
          <div className="space-y-6">
            <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-800/40 flex items-start gap-3">
              <Sparkles className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
              <div className="text-xs text-neutral-300 leading-relaxed">
                <span className="font-semibold text-white">Вывод для команды: </span>
                Для генерации конспектов, извлечения дедлайнов и вывода LaTeX формул безоговорочным победителем является{' '}
                <strong className="text-indigo-300">Qwen 2.5 7B Instruct (в квантовании Q4_K_M)</strong>. Она превосходит все аналоги по качеству математических формул (9.8/10) и требует всего ~4.8 ГБ оперативной памяти.
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4">
              {TOP_5_LLM_MODELS.map((model, idx) => (
                <div
                  key={model.id}
                  className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-neutral-800 text-neutral-300 text-xs font-bold flex items-center justify-center font-mono">
                        {idx + 1}
                      </span>
                      <div>
                        <h3 className="text-sm font-bold text-white">
                          {model.name}
                        </h3>
                        <div className="text-[11px] text-neutral-400">
                          {model.developer} · Параметров: {model.parameters}
                        </div>
                      </div>
                    </div>

                    <a
                      href={`https://huggingface.co/${model.huggingFaceId}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 bg-neutral-950 px-2.5 py-1 rounded border border-neutral-800 self-start sm:self-center"
                    >
                      <span>HF: {model.huggingFaceId}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>

                  {/* LLM Quality Radar Scores */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Русский язык</div>
                      <div className="font-mono text-sm font-bold text-emerald-400 mt-0.5">
                        {model.russianQuality} / 10
                      </div>
                      <div className="text-[10px] text-neutral-400">Грамматика и падежи</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">LaTeX & Формулы</div>
                      <div className="font-mono text-sm font-bold text-indigo-300 mt-0.5">
                        {model.mathLatexQuality} / 10
                      </div>
                      <div className="text-[10px] text-neutral-400">Матрицы, интегралы</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Парсинг дедлайнов</div>
                      <div className="font-mono text-sm font-bold text-amber-400 mt-0.5">
                        {model.taskExtractionQuality} / 10
                      </div>
                      <div className="text-[10px] text-neutral-400">Поиск дат в устной речи</div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-850">
                      <div className="text-[10px] text-neutral-500 uppercase">Память (Q4_K_M)</div>
                      <div className="font-mono text-sm font-bold text-white mt-0.5">
                        {model.ramQ4}
                      </div>
                      <div className="text-[10px] text-neutral-400">Контекст: {model.contextLength}</div>
                    </div>
                  </div>

                  <p className="text-xs text-neutral-300 leading-relaxed">
                    {model.description}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-neutral-800 text-[11px] text-neutral-400">
                    <div>
                      <strong>GGUF файл: </strong>
                      <code className="px-1.5 py-0.5 rounded bg-neutral-950 font-mono text-indigo-300">
                        {model.recommendedGguf}
                      </code>
                    </div>
                    <div>
                      <strong>Лучшее применение: </strong>
                      <span>{model.bestUseFor}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SECTION 3: NOISE & HARDWARE SIMULATOR */}
        {activeSection === 'simulator' && (
          <div className="space-y-6">
            <div className="p-6 rounded-xl bg-neutral-900 border border-neutral-800 space-y-6">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-indigo-400" />
                  Интерактивный симулятор аудитории и студенческого железа
                </h3>
                <p className="text-xs text-neutral-400 mt-1">
                  Настройте уровень шума в аудитории и тип ноутбука, чтобы увидеть расчетную точность и время обработки
                </p>
              </div>

              {/* Sliders */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
                {/* SNR Slider */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-neutral-300 font-medium">Шум (Отношение сигнал/шум, SNR):</span>
                    <span className="font-mono text-indigo-300 font-bold">{simNoiseSnr} dB</span>
                  </div>
                  <input
                    type="range"
                    min={5}
                    max={30}
                    step={1}
                    value={simNoiseSnr}
                    onChange={(e) => setSimNoiseSnr(Number(e.target.value))}
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-[10px] text-neutral-500">
                    <span>5 dB (Гул, шепот)</span>
                    <span>15 dB (Обычная пара)</span>
                    <span>30 dB (Студия)</span>
                  </div>
                </div>

                {/* Lecture length */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-neutral-300 font-medium">Длительность лекции:</span>
                    <span className="font-mono text-indigo-300 font-bold">{simLectureLengthMin} минут</span>
                  </div>
                  <input
                    type="range"
                    min={20}
                    max={180}
                    step={10}
                    value={simLectureLengthMin}
                    onChange={(e) => setSimLectureLengthMin(Number(e.target.value))}
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-[10px] text-neutral-500">
                    <span>20 мин (Семинар)</span>
                    <span>80-90 мин (Пара)</span>
                    <span>180 мин (Блок)</span>
                  </div>
                </div>

                {/* Hardware selector */}
                <div className="space-y-2">
                  <label className="block text-xs font-medium text-neutral-300">
                    Аппаратное обеспечение:
                  </label>
                  <select
                    value={simHardware}
                    onChange={(e) => setSimHardware(e.target.value as unknown as 'gpu_mid')}
                    className="w-full px-3 py-1.5 text-xs bg-neutral-950 border border-neutral-800 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="gpu_mid">Ноутбук с NVIDIA RTX 3050/4050 (4-6 ГБ VRAM)</option>
                    <option value="gpu_high">Мощный ПК / RTX 3060/4070+ (8-16 ГБ VRAM)</option>
                    <option value="apple_silicon">Apple Silicon Mac (M1/M2/M3 с Metal MPS)</option>
                    <option value="cpu">Бюджетный ноутбук без GPU (Чистый Intel/AMD CPU)</option>
                  </select>
                  <div className="text-[10px] text-neutral-500">
                    Определяет Real-Time Factor (RTF)
                  </div>
                </div>
              </div>

              {/* Simulation Result Cards */}
              <div className="p-4 rounded-xl bg-neutral-950 border border-neutral-800 grid grid-cols-1 sm:grid-cols-4 gap-4 text-center">
                <div className="p-3 rounded-lg bg-neutral-900 border border-neutral-850">
                  <div className="text-[10px] text-neutral-400 uppercase">Faster-Whisper Turbo</div>
                  <div className="text-xl font-bold font-mono text-indigo-400 mt-1">
                    {simResults.fwWer}% WER
                  </div>
                  <div className="text-[10px] text-neutral-500 mt-0.5">Точность ~{(100 - simResults.fwWer).toFixed(1)}%</div>
                </div>

                <div className="p-3 rounded-lg bg-neutral-900 border border-neutral-850">
                  <div className="text-[10px] text-neutral-400 uppercase">GigaAM v2 (Sber)</div>
                  <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                    {simResults.gigaWer}% WER
                  </div>
                  <div className="text-[10px] text-neutral-500 mt-0.5">Лидер в шуме</div>
                </div>

                <div className="p-3 rounded-lg bg-neutral-900 border border-neutral-850">
                  <div className="text-[10px] text-neutral-400 uppercase">Whisper.cpp (Q5_0)</div>
                  <div className="text-xl font-bold font-mono text-amber-400 mt-1">
                    {simResults.cppWer}% WER
                  </div>
                  <div className="text-[10px] text-neutral-500 mt-0.5">Лучше для старых CPU</div>
                </div>

                <div className="p-3 rounded-lg bg-neutral-900 border border-neutral-850">
                  <div className="text-[10px] text-neutral-400 uppercase">Время обработки</div>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    ~{simResults.processTimeMinutes} мин
                  </div>
                  <div className="text-[10px] text-neutral-500 mt-0.5">Для лекции {simLectureLengthMin} мин</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 4: EDUCATIONAL KNOWLEDGE HUB */}
        {activeSection === 'guide' && (
          <div className="space-y-6">
            
            {/* 1. Quantization Guide */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">{QUANTIZATION_GUIDE.title}</h3>
              </div>
              <p className="text-xs text-neutral-300 leading-relaxed">{QUANTIZATION_GUIDE.summary}</p>
              
              <div className="space-y-1.5 text-xs text-neutral-300">
                {QUANTIZATION_GUIDE.benefits.map((b, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                    <span>{b}</span>
                  </div>
                ))}
              </div>

              {/* Quantization Table */}
              <div className="overflow-x-auto pt-2">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-neutral-800 text-[10px] text-neutral-400 uppercase">
                      <th className="py-2 pr-4">Формат квантования</th>
                      <th className="py-2 pr-4">Бит на вес</th>
                      <th className="py-2 pr-4">Размер в RAM</th>
                      <th className="py-2 pr-4">Потеря точности (Perplexity)</th>
                      <th className="py-2">Рекомендация для проекта</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-850 font-mono text-[11px]">
                    {QUANTIZATION_GUIDE.levels.map((lvl, lIdx) => (
                      <tr key={lIdx} className="hover:bg-neutral-850/50">
                        <td className="py-2 pr-4 font-bold text-indigo-300">{lvl.type}</td>
                        <td className="py-2 pr-4 text-neutral-300">{lvl.bits} бит</td>
                        <td className="py-2 pr-4 text-neutral-300">{lvl.vramMultiplier}</td>
                        <td className="py-2 pr-4 text-neutral-400">{lvl.perplexityLoss}</td>
                        <td className="py-2 text-neutral-200 font-sans">{lvl.recommendation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 2. Context Length */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
              <div className="flex items-center gap-2">
                <Clock className="w-5 h-5 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">{CONTEXT_LENGTH_GUIDE.title}</h3>
              </div>
              <p className="text-xs text-neutral-300 leading-relaxed">{CONTEXT_LENGTH_GUIDE.summary}</p>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {CONTEXT_LENGTH_GUIDE.contextNeeds.map((item, idx) => (
                  <div key={idx} className="p-3 rounded-lg bg-neutral-950 border border-neutral-800">
                    <div className="font-mono font-bold text-indigo-300 text-xs">{item.window}</div>
                    <div className="text-neutral-300 text-[11px] mt-1">{item.coverage}</div>
                    <div className="text-[10px] text-emerald-400 mt-1">Оценка: {item.verdict}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* 3. Hugging Face */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
              <div className="flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-indigo-400" />
                <h3 className="text-sm font-bold text-white">{HUGGINGFACE_GUIDE.title}</h3>
              </div>
              <p className="text-xs text-neutral-300 leading-relaxed">{HUGGINGFACE_GUIDE.summary}</p>
              
              <div className="space-y-1.5 text-xs text-neutral-300">
                {HUGGINGFACE_GUIDE.whyWeNeedIt.map((why, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <span className="w-4 h-4 rounded-full bg-neutral-800 text-[10px] flex items-center justify-center text-neutral-300 font-mono shrink-0 mt-0.5">
                      {idx + 1}
                    </span>
                    <span>{why}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 4. Habr Article Analysis */}
            <div className="p-5 rounded-xl bg-neutral-900 border border-neutral-800 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ExternalLink className="w-5 h-5 text-indigo-400" />
                  <h3 className="text-sm font-bold text-white">{HABR_ARTICLE_ANALYSIS.title}</h3>
                </div>
                <a
                  href="https://habr.com/ru/articles/945086/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs font-mono text-indigo-400 hover:text-indigo-300"
                >
                  habr.com/ru/articles/945086
                </a>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {HABR_ARTICLE_ANALYSIS.keyTakeaways.map((takeaway, idx) => (
                  <div key={idx} className="p-3.5 rounded-lg bg-neutral-950 border border-neutral-800 space-y-1">
                    <div className="font-semibold text-white text-xs">{takeaway.point}</div>
                    <div className="text-neutral-400 text-[11px] leading-relaxed">{takeaway.text}</div>
                  </div>
                ))}
              </div>
            </div>

          </div>
        )}

      </div>
    </div>
  );
};
