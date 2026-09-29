import { AsrModelInfo, LlmModelInfo } from '../types';

export const TOP_5_ASR_MODELS: AsrModelInfo[] = [
  {
    id: 'faster-whisper-turbo',
    name: 'Faster-Whisper (Large-v3-Turbo)',
    developer: 'Systran & OpenAI',
    architecture: 'Encoder-Decoder Transformer (CTranslate2)',
    huggingFaceId: 'Systran/faster-whisper-large-v3-turbo',
    parameters: '809M',
    werClean: 5.4,
    werNoisy: 11.2,
    werRussian: 5.8,
    rtfCpu: 0.28,
    rtfGpu: 0.04,
    vramFp16: '3.1 GB',
    vramInt8: '1.8 GB',
    contextOrChunk: '30-секундные скользящие окна с контекстной перекрытием',
    quantizationSupport: ['float16', 'int8_float16', 'int8', 'int8_bfloat16'],
    bestUseFor: 'Универсальный стандарт для ноутбуков с GPU (NVIDIA GTX/RTX или Apple Silicon). Идеальный баланс скорости и понимания русского языка.',
    pros: [
      'В 4-8 раз быстрее оригинального openai/whisper за счет CTranslate2',
      'Отличная пунктуация и разбиение на предложения',
      'Поддерживает квантование INT8 прямо «из коробки» без потери качества (WER деградирует всего на 0.2%)',
      'Встроенная поддержка таймкодов на уровне слов (word-level timestamps)'
    ],
    cons: [
      'Может галлюцинировать при долгих паузах тишины (требуется Silero VAD фильтр)',
      'На чистом CPU без AVX-512 работает медленнее, чем whisper.cpp'
    ]
  },
  {
    id: 'gigaam-v2',
    name: 'GigaAM v2 (Sber AI)',
    developer: 'SberDevices & SaluteDevices',
    architecture: 'Conformer-CTC / RNN-T (NeMo)',
    huggingFaceId: 'salute-devices/GigaAM-v2',
    parameters: '240M - 600M',
    werClean: 4.2,
    werNoisy: 9.8,
    werRussian: 4.1,
    rtfCpu: 0.15,
    rtfGpu: 0.02,
    vramFp16: '2.0 GB',
    vramInt8: '1.1 GB',
    contextOrChunk: 'Потоковый / чанковый CTC с неограниченным контекстом',
    quantizationSupport: ['FP16', 'INT8 (ONNX Runtime)', 'TensorRT'],
    bestUseFor: 'Лучшее распознавание русской речи, академических терминов, фамилий ученых и студенческого сленга.',
    pros: [
      'Обучена на колоссальном датасете русской речи (десятки тысяч часов)',
      'Не подвержена галлюцинациям в тишине (в отличие от авторегрессионного Whisper)',
      'Рекордно низкая задержка (RTF 0.02 на GPU) — подходит для транскрибации прямо «на лету»',
      'Очень компактная (Conformer эффективнее стандартного Transformer в 2 раза)'
    ],
    cons: [
      'Пунктуацию и заглавные буквы нужно восстанавливать отдельной моделью (например, sberbank-ai/ru-punctuator)',
      'Хуже распознает фрагменты на чистом английском языке (модель моноязычная)'
    ]
  },
  {
    id: 'whisper-cpp',
    name: 'Whisper.cpp (Medium / Q5_0)',
    developer: 'Georgi Gerganov',
    architecture: 'GGML / C++ Optimized Transformer',
    huggingFaceId: 'ggerganov/whisper.cpp (medium.bin)',
    parameters: '769M',
    werClean: 6.8,
    werNoisy: 13.5,
    werRussian: 7.2,
    rtfCpu: 0.22,
    rtfGpu: 0.06,
    vramFp16: '2.8 GB',
    vramInt8: '1.4 GB (RAM: 950 MB)',
    contextOrChunk: '30s sliding audio chunk',
    quantizationSupport: ['Q4_0', 'Q4_1', 'Q5_0', 'Q5_1', 'Q8_0', 'FP16'],
    bestUseFor: 'Старые студенческие ноутбуки без дискретной видеокарты (Intel Iris, AMD Ryzen, старые Core i5/i7).',
    pros: [
      'Чистый C/C++ без зависимостей от PyTorch и тяжелого Python рантайма',
      'Использует векторные инструкции AVX2, AVX-512, Neon и Metal',
      'Экстремально низкое потребление оперативной памяти при квантовании Q5_0 (меньше 1 ГБ)',
      'Идеально подходит для компиляции в автономные исполняемые файлы (PySide6 + C-bindings)'
    ],
    cons: [
      'Квантование Q4_0 дает заметный прирост ошибок на сложном звуке (WER +2.5%)',
      'Менее гибкий пайплайн предобработки аудио по сравнению с Python-библиотеками'
    ]
  },
  {
    id: 'sensevoice-small',
    name: 'SenseVoice-Small',
    developer: 'Alibaba FunASR',
    architecture: 'Non-Autoregressive Audio Tokenizer',
    huggingFaceId: 'FunAudioLLM/SenseVoiceSmall',
    parameters: '234M',
    werClean: 6.1,
    werNoisy: 10.9,
    werRussian: 6.4,
    rtfCpu: 0.12,
    rtfGpu: 0.015,
    vramFp16: '1.2 GB',
    vramInt8: '700 MB',
    contextOrChunk: 'Неавторегрессионный инференс (Non-autoregressive CTC)',
    quantizationSupport: ['ONNX FP16', 'INT8', 'TorchScript'],
    bestUseFor: 'Семинары и дискуссии: умеет определять смех, аплодисменты, фоновые шумы и эмоциональный тон лектора.',
    pros: [
      'В 5-15 раз быстрее Whisper Large за счет неавторегрессионной архитектуры',
      'Детектирует аудиособытия (Auditory Events: кашель, стук дверей, музыка, вздохи)',
      'Прекрасно работает на слабых процессорах смартфонов и микрокомпьютеров (Raspberry Pi 5)',
      'Компактный размер весов (~450 МБ)'
    ],
    cons: [
      'Меньшая точность на редких математических терминах по сравнению с Large-v3-Turbo',
      'Русский язык поддерживается хорошо, но хуже, чем у GigaAM'
    ]
  },
  {
    id: 'silero-vad-asr',
    name: 'Silero VAD + Speech-to-Text',
    developer: 'Silero Models (Snakers4)',
    architecture: 'Lightweight Conv-RNN + CTC',
    huggingFaceId: 'snakers4/silero-models',
    parameters: '45M - 110M',
    werClean: 7.9,
    werNoisy: 12.1,
    werRussian: 7.4,
    rtfCpu: 0.04,
    rtfGpu: 0.008,
    vramFp16: '450 MB',
    vramInt8: '200 MB',
    contextOrChunk: 'Потоковый микро-чанк (30мс - 100мс)',
    quantizationSupport: ['ONNX INT8', 'JIT', 'TorchScript'],
    bestUseFor: 'Пре-процессинг и фильтрация тишины/шума: VAD (Voice Activity Detection) обязателен перед подачей в Whisper.',
    pros: [
      'Silero VAD — мировой стандарт детекции голоса (<1 мс время отклика, 2 МБ размер)',
      'Отрезает 30-50% тишины и кашля из записи лекции, экономя время ASR вдвое',
      'Не требует GPU, работает даже на умных часах и микроконтроллерах'
    ],
    cons: [
      'Собственный модуль ASR уступает Whisper по лексическому запасу формул и иностранных заимствований'
    ]
  }
];

export const TOP_5_LLM_MODELS: LlmModelInfo[] = [
  {
    id: 'qwen-2.5-7b',
    name: 'Qwen 2.5 7B Instruct (GGUF)',
    developer: 'Alibaba Cloud',
    huggingFaceId: 'Qwen/Qwen2.5-7B-Instruct-GGUF',
    parameters: '7.6B',
    contextLength: '32,768 (до 128k)',
    ramQ4: '4.8 GB RAM',
    russianQuality: 9.6,
    mathLatexQuality: 9.8,
    taskExtractionQuality: 9.5,
    recommendedGguf: 'qwen2.5-7b-instruct-q4_k_m.gguf',
    bestUseFor: 'Основная рекомендация! Абсолютный лидер по генерации LaTeX формул, пониманию русского языка и структурированию лекций.',
    description: 'Идеально генерирует сложные математические матрицы, пределы, интегралы и безошибочно парсит даты дедлайнов из устной речи.'
  },
  {
    id: 'llama-3.2-3b',
    name: 'Llama 3.2 3B Instruct (GGUF)',
    developer: 'Meta AI',
    huggingFaceId: 'meta-llama/Llama-3.2-3B-Instruct',
    parameters: '3.2B',
    contextLength: '128,000 токенов',
    ramQ4: '2.2 GB RAM',
    russianQuality: 8.2,
    mathLatexQuality: 8.0,
    taskExtractionQuality: 8.8,
    recommendedGguf: 'llama-3.2-3b-instruct-q4_k_m.gguf',
    bestUseFor: 'Сверхбыстрая работа на слабых ноутбуках (8 ГБ общей оперативной памяти).',
    description: 'Очень легкая модель, выдающая 40-70 токенов/сек на обычном современном CPU. Надежно выделяет списки дел и даты.'
  },
  {
    id: 'deepseek-r1-distill-qwen-7b',
    name: 'DeepSeek R1 Distill Qwen 7B',
    developer: 'DeepSeek AI',
    huggingFaceId: 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF',
    parameters: '7.6B',
    contextLength: '32,768 токенов',
    ramQ4: '5.1 GB RAM',
    russianQuality: 9.2,
    mathLatexQuality: 9.9,
    taskExtractionQuality: 9.6,
    recommendedGguf: 'deepseek-r1-distill-qwen-7b-q4_k_m.gguf',
    bestUseFor: 'Сложные технические лекции (физмат, теорфиз, матстат, алгоритмы).',
    description: 'Использует цепочку рассуждений (Chain-of-Thought) для самопроверки формул и вывода промежуточных шагов доказательств теорем.'
  },
  {
    id: 'mistral-nemo-12b',
    name: 'Mistral Nemo 12B Instruct',
    developer: 'Mistral AI & NVIDIA',
    huggingFaceId: 'mistralai/Mistral-Nemo-Instruct-2407',
    parameters: '12.2B',
    contextLength: '128,000 токенов',
    ramQ4: '7.5 GB RAM',
    russianQuality: 8.9,
    mathLatexQuality: 8.7,
    taskExtractionQuality: 9.4,
    recommendedGguf: 'mistral-nemo-instruct-2407-q4_k_m.gguf',
    bestUseFor: 'Длинные потоковые лекции по 3-4 часа (за счет 128k контекста с токенизатором Tekken).',
    description: 'Новый токенизатор Tekken сжимает текст на 30% эффективнее других, позволяя помещать огромные объемы стенограмм.'
  },
  {
    id: 'gemma-2-9b',
    name: 'Gemma 2 9B IT (GGUF)',
    developer: 'Google DeepMind',
    huggingFaceId: 'google/gemma-2-9b-it-GGUF',
    parameters: '9.2B',
    contextLength: '8,192 токенов',
    ramQ4: '5.9 GB RAM',
    russianQuality: 8.8,
    mathLatexQuality: 9.1,
    taskExtractionQuality: 9.0,
    recommendedGguf: 'gemma-2-9b-it-q4_k_m.gguf',
    bestUseFor: 'Литературный конспект и академическая суммаризация без воды.',
    description: 'Архитектура с чередующимися локальными и глобальными слоями внимания. Отличается высоким качеством языка и четким стилем.'
  }
];

export const QUANTIZATION_GUIDE = {
  title: 'Что такое квантование (Quantization)?',
  summary: 'Квантование — это процесс сжатия весов нейросети путем уменьшения точности чисел (например, из 32-битных или 16-битных чисел с плавающей точкой FP32/FP16 в 8-битные INT8 или 4-битные Q4_K_M).',
  benefits: [
    'Снижение требований к памяти: Модель на 7 миллиардов параметров в FP16 требует ~14-16 ГБ VRAM, а после квантования в Q4_K_M — всего 4.8 ГБ RAM!',
    'Ускорение работы: 4-битные и 8-битные операции выполняются значительно быстрее благодаря уменьшению пропускной способности памяти (memory bandwidth bottleneck).',
    'Потери качества < 1%: Современные алгоритмы (AWQ, GPTQ, GGUF k-quants) квантуют только некритичные веса, оставляя ключевые слои в более высокой точности.'
  ],
  levels: [
    { type: 'FP16 / BF16', bits: 16, vramMultiplier: '1.0x (14 ГБ)', perplexityLoss: '0% (Базовая точность)', recommendation: 'Только если есть мощная GPU (RTX 3090/4090)' },
    { type: 'INT8 / Q8_0', bits: 8, vramMultiplier: '0.5x (~7.5 ГБ)', perplexityLoss: '< 0.05% (Неотличимо на глаз)', recommendation: 'Идеально для Faster-Whisper ASR' },
    { type: 'Q5_K_M', bits: 5, vramMultiplier: '0.38x (~5.8 ГБ)', perplexityLoss: '< 0.2%', recommendation: 'Отличный выбор для точной математики' },
    { type: 'Q4_K_M', bits: 4.5, vramMultiplier: '0.30x (~4.8 ГБ)', perplexityLoss: '< 0.5%', recommendation: 'Золотой стандарт для большинства студентов (8-16 ГБ RAM)' },
    { type: 'Q3_K_S', bits: 3.4, vramMultiplier: '0.22x (~3.6 ГБ)', perplexityLoss: '1.5 - 3.0%', recommendation: 'Для крайне слабых устройств' }
  ]
};

export const CONTEXT_LENGTH_GUIDE = {
  title: 'Длина контекста (Context Length)',
  summary: 'Длина контекста — это максимальное количество токенов (слов/символов), которое нейросеть может удержать в оперативной памяти одновременно во время анализа.',
  tokenRules: [
    '1 токен ≈ 3-4 буквы на русском/английском языке (или ~0.75 слова).',
    '1 пара лекции (80-90 минут) при обычной речи лектора (120-140 слов/мин) дает около 10 000 - 12 000 слов.',
    'В токенах для русского языка это составляет ~16 000 - 20 000 токенов стенограммы.'
  ],
  contextNeeds: [
    { window: '4,096 токенов', coverage: 'Короткий доклад или опрос на 15-20 минут', verdict: 'Мало для университетской пары' },
    { window: '8,192 токенов', coverage: 'Семинар на 45 минут или разбиение лекции на части', verdict: 'Требует разбивки на блоки (chunking)' },
    { window: '32,768 токенов (Qwen 2.5)', coverage: 'Полная пара на 1.5 - 2 часа целиком в один проход!', verdict: 'Оптимально для студенческого диктофона' },
    { window: '128,000 токенов (Llama 3.2 / Mistral)', coverage: 'Весь день лекций или 4-6 пар подряд без потери контекста', verdict: 'Максимальный комфорт для сессии' }
  ]
};

export const HUGGINGFACE_GUIDE = {
  title: 'Что такое Hugging Face (huggingface.co)?',
  summary: 'Hugging Face — это всемирный «GitHub для искусственного интеллекта». Главный репозиторий открытых весов нейросетей, токенизаторов, датасетов и инструментов инференса.',
  whyWeNeedIt: [
    'Хранилище открытых весов: Все наши локальные модели (Faster-Whisper, GigaAM, Qwen, Llama GGUF) бесплатно скачиваются именно с huggingface.co.',
    'Автономность (Офлайн-режим): Модели скачиваются один раз в локальную папку (~/.cache/huggingface/), после чего диктофон работает 100% без интернета в подвальных аудиториях.',
    'Готовые GGUF квантованные файлы: Сообщество (TheBloke, bartowski, unsloth) выкладывает готовые сжатые версии для моментального запуска в llama.cpp/PySide6.',
    'Python-библиотека `huggingface_hub`: Позволяет в 3 строчки кода реализовать автоматическую загрузку и верификацию контрольных сумм в нашем приложении.'
  ]
};

export const HABR_ARTICLE_ANALYSIS = {
  title: 'Разбор статьи с Хабра: Локальные нейросети без облака',
  source: 'habr.com/ru/articles/945086',
  keyTakeaways: [
    {
      point: '1. Экосистема llama.cpp и формат GGUF',
      text: 'Формат GGUF заменил старый GGML. Он позволяет хранить метаданные, токенизатор и квантованные веса в одном файле. Запуск через C++ библиотеку llama-cpp-python обеспечивает работу на чистом CPU и GPU без гигантского PyTorch.'
    },
    {
      point: '2. Разгрузка слоев на GPU (GPU Offloading: n_gpu_layers)',
      text: 'Если у студента бюджетная видеокарта (например, RTX 3050 с 4 ГБ VRAM), модель 7B не влезет целиком. llama.cpp позволяет отправить 20 слоев в GPU, а остальные 12 слоев оставить в RAM CPU. Это дает скорость 15-25 токенов/сек!'
    },
    {
      point: '3. CTranslate2 для Whisper',
      text: 'Для распознавания речи использование чистого PyTorch неоправданно медленно. CTranslate2 (на котором сделан faster-whisper) сжимает вычисления и уменьшает задержку в 4 раза при идентичном качестве.'
    },
    {
      point: '4. Полная приватность и автономность',
      text: 'Ключевое бизнес-преимущество проекта: студенты и преподаватели не боятся утечки закрытых лекций или вопросов, так как ни один байт звука не покидает устройство.'
    }
  ]
};
