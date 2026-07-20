/**
 * Natural-sounding speech helpers.
 * Prefers OS neural/natural voices; falls back gracefully.
 * Optional backend Kokoro path plays WAV via HTMLAudioElement.
 */

export type SpeakHandlers = {
  onStart?: () => void;
  onEnd?: () => void;
  onBoundary?: () => void;
  /** Called with the sentence currently being spoken; null when speech ends. */
  onSubtitle?: (sentence: string | null) => void;
};

export type SpeakOptions = SpeakHandlers & {
  rate?: number;
  pitch?: number;
  level?: "beginner" | "elementary" | "intermediate";
  /** Kokoro / avatar voice id (e.g. af_heart) — used for ranking hints */
  voiceId?: string;
  /** Prefer this BCP-47 lang when picking browser voices */
  lang?: string;
  /** Play pre-synthesized audio (e.g. Kokoro WAV as data URL or blob URL) */
  audioUrl?: string | null;
};

type VoiceLike = {
  name: string;
  lang: string;
  localService?: boolean;
  default?: boolean;
};

let voicesReady: Promise<SpeechSynthesisVoice[]> | null = null;
let activeAudio: HTMLAudioElement | null = null;
let speakGeneration = 0;

function ensureVoices(): Promise<SpeechSynthesisVoice[]> {
  if (!("speechSynthesis" in window)) return Promise.resolve([]);
  const existing = window.speechSynthesis.getVoices();
  if (existing.length) return Promise.resolve(existing);
  if (voicesReady) return voicesReady;
  voicesReady = new Promise((resolve) => {
    const done = () => {
      window.speechSynthesis.removeEventListener("voiceschanged", done);
      resolve(window.speechSynthesis.getVoices());
    };
    window.speechSynthesis.addEventListener("voiceschanged", done);
    // Fallback if event never fires
    window.setTimeout(done, 400);
  });
  return voicesReady;
}

/** Exported for unit tests — score higher = more natural. */
export function scoreVoiceNaturalness(voice: VoiceLike, gender: string, lang = "en"): number {
  const name = voice.name || "";
  const vlang = (voice.lang || "").toLowerCase();
  let score = 0;

  if (!vlang.startsWith(lang.toLowerCase().slice(0, 2))) return -1000;

  // Strongly prefer neural / natural / online voices (Edge, modern Windows, Chrome)
  if (/natural|neural|online|premium|enhanced|super|wavenet|studio|generative/i.test(name)) {
    score += 80;
  }
  // Modern Microsoft named neural voices
  if (
    /aria|jenny|guy|davis|ryan|sonia|sara|tony|nancy|jane|jason|christopher|eric|michelle|monica|steffan|andrew|emma|brian/i.test(
      name
    )
  ) {
    score += 55;
  }
  // Google / Apple quality voices
  if (/google/i.test(name)) score += 45;
  if (/samantha|karen|moira|daniel \(enhanced\)|fiona|victoria|alex|stephanie|susan/i.test(name)) {
    score += 35;
  }

  // Penalize clearly robotic / novelty / compact voices
  if (/compact|eloquence|whisper|novelty|zarvox|trinoids|bad news|good news|bells|bubbles|boing|cellos|organ|princess|pipe|ralph|junior|albert|bahh|boing/i.test(name)) {
    score -= 90;
  }
  if (/desktop|mobile|siri/i.test(name) && !/natural|neural/i.test(name)) score -= 15;
  // Older Windows defaults tend to sound flat
  if (/microsoft david|microsoft zira|microsoft mark|microsoft hazel/i.test(name) && !/natural|neural|online/i.test(name)) {
    score -= 25;
  }

  // Gender fit
  const femaleHint = /female|woman|girl|zira|samantha|susan|karen|moira|fiona|victoria|aria|jenny|sonia|sara|nancy|jane|michelle|monica|emma|stephanie/i;
  const maleHint = /male|man|boy|david|mark|daniel|alex|george|fred|guy|davis|ryan|tony|jason|christopher|eric|steffan|andrew|brian/i;
  if (gender === "girl") {
    if (femaleHint.test(name)) score += 30;
    if (maleHint.test(name) && !femaleHint.test(name)) score -= 40;
  } else if (gender === "boy") {
    if (maleHint.test(name)) score += 30;
    if (femaleHint.test(name) && !maleHint.test(name)) score -= 40;
  }

  // Prefer en-US / en-GB for kids English tutoring
  if (/^en-us/i.test(vlang)) score += 12;
  else if (/^en-gb/i.test(vlang)) score += 8;
  else if (/^en/i.test(vlang)) score += 5;

  // Remote neural voices are usually better than local legacy
  if (voice.localService === false) score += 10;

  return score;
}

export function pickNaturalVoice(
  voices: VoiceLike[],
  gender: string,
  lang = "en"
): VoiceLike | undefined {
  const english = voices.filter((v) => (v.lang || "").toLowerCase().startsWith("en"));
  const pool = english.length ? english : voices;
  if (!pool.length) return undefined;
  return [...pool].sort(
    (a, b) => scoreVoiceNaturalness(b, gender, lang) - scoreVoiceNaturalness(a, gender, lang)
  )[0];
}

/** Soften text for TTS: keep kid-friendly pacing cues. */
export function prepareSpeakText(raw: string): string {
  let text = raw.replace(/\s+/g, " ").trim();
  if (!text) return "";
  // Drop dense tool dump lines that sound awful when spoken
  text = text
    .split("\n")
    .filter((line) => !/^(open_app|open_website|set_volume|computer_|list_windows|start_timer):/i.test(line.trim()))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  // Ensure terminal punctuation so synthesizers don't drone
  if (text && !/[.!?…]$/.test(text)) text += ".";
  return text;
}

export function splitSpeakChunks(text: string): string[] {
  const prepared = prepareSpeakText(text);
  if (!prepared) return [];
  // Split on sentence boundaries; keep short phrases together
  const parts = prepared.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [prepared];
  return parts.map((p) => p.trim()).filter(Boolean);
}

function levelRate(level: SpeakOptions["level"], override?: number): number {
  if (override != null) return override;
  // Avoid ultra-slow rates — they sound robotic. Beginners still get a bit more space.
  if (level === "beginner") return 0.92;
  if (level === "elementary") return 0.97;
  return 1.0;
}

function levelPitch(gender: string, override?: number): number {
  if (override != null) return override;
  if (gender === "girl") return 1.06;
  if (gender === "boy") return 0.94;
  return 1.0;
}

function stopAllSpeech() {
  speakGeneration += 1;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  if (activeAudio) {
    activeAudio.pause();
    activeAudio.src = "";
    activeAudio = null;
  }
}

async function playAudioUrl(url: string, text: string, gender: string, handlers: SpeakOptions): Promise<void> {
  // Approximate per-sentence subtitle timing: proportional share of the
  // audio duration by sentence length (Kokoro gives us one WAV for all).
  const sentences = splitSpeakChunks(text);
  const totalChars = sentences.reduce((sum, s) => sum + s.length, 0) || 1;

  const played = await new Promise<boolean>((resolve) => {
    const audio = new Audio(url);
    activeAudio = audio;
    let cueTimers: number[] = [];
    let settled = false;

    const scheduleSubtitles = () => {
      if (!handlers.onSubtitle || !sentences.length) return;
      const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
      handlers.onSubtitle(sentences[0]);
      if (duration <= 0 || sentences.length === 1) return;
      let elapsed = 0;
      for (let i = 0; i < sentences.length - 1; i++) {
        elapsed += (sentences[i].length / totalChars) * duration;
        const next = sentences[i + 1];
        cueTimers.push(
          window.setTimeout(() => {
            if (activeAudio === audio) handlers.onSubtitle?.(next);
          }, elapsed * 1000)
        );
      }
    };

    const finishOk = () => {
      if (settled) return;
      settled = true;
      cueTimers.forEach((t) => window.clearTimeout(t));
      if (activeAudio === audio) activeAudio = null;
      handlers.onSubtitle?.(null);
      handlers.onEnd?.();
      resolve(true);
    };

    const failToFallback = () => {
      if (settled) return;
      settled = true;
      cueTimers.forEach((t) => window.clearTimeout(t));
      if (activeAudio === audio) {
        activeAudio.pause();
        activeAudio.src = "";
        activeAudio = null;
      }
      resolve(false);
    };

    audio.onplay = () => {
      handlers.onStart?.();
      scheduleSubtitles();
    };
    audio.ontimeupdate = () => handlers.onBoundary?.();
    audio.onended = finishOk;
    audio.onerror = failToFallback;
    void audio.play().then(
      () => {
        /* playing */
      },
      () => failToFallback()
    );
  });

  if (!played) {
    // Autoplay policies often block HTMLAudioElement without a gesture;
    // browser speechSynthesis is usually still allowed for coach lines.
    const gen = speakGeneration;
    await speakBrowserChunks(text, gender, { ...handlers, audioUrl: null }, gen);
  }
}

async function speakBrowserChunks(
  text: string,
  gender: string,
  handlers: SpeakOptions,
  gen: number
): Promise<void> {
  const chunks = splitSpeakChunks(text);
  if (!chunks.length) {
    handlers.onEnd?.();
    return;
  }

  const voices = await ensureVoices();
  const pick = pickNaturalVoice(voices, gender, handlers.lang || "en");
  const rate = levelRate(handlers.level, handlers.rate);
  const pitch = levelPitch(gender, handlers.pitch);

  let started = false;

  for (let i = 0; i < chunks.length; i++) {
    if (gen !== speakGeneration) return;
    const chunk = chunks[i];
    handlers.onSubtitle?.(chunk);
    await new Promise<void>((resolve) => {
      const utter = new SpeechSynthesisUtterance(chunk);
      utter.rate = rate;
      utter.pitch = pitch;
      utter.volume = 1;
      if (pick && "voiceURI" in pick) {
        utter.voice = pick as SpeechSynthesisVoice;
        utter.lang = (pick as SpeechSynthesisVoice).lang || "en-US";
      } else {
        utter.lang = "en-US";
      }
      utter.onstart = () => {
        if (!started) {
          started = true;
          handlers.onStart?.();
        }
      };
      utter.onboundary = () => handlers.onBoundary?.();
      utter.onend = () => resolve();
      utter.onerror = () => resolve();
      window.speechSynthesis.speak(utter);
    });
    // Brief breath between sentences (natural cadence)
    if (i < chunks.length - 1 && gen === speakGeneration) {
      await new Promise((r) => window.setTimeout(r, 120));
    }
  }
  if (gen === speakGeneration) {
    handlers.onSubtitle?.(null);
    handlers.onEnd?.();
  }
}

/**
 * Speak text as naturally as the platform allows.
 * If `audioUrl` is provided (Kokoro / cloud TTS), that is preferred.
 */
export function speakText(text: string, gender: string, handlers: SpeakOptions = {}) {
  stopAllSpeech();
  const gen = speakGeneration;

  if (handlers.audioUrl) {
    void playAudioUrl(handlers.audioUrl, text, gender, {
      ...handlers,
      onEnd: () => {
        if (gen === speakGeneration) handlers.onEnd?.();
      },
    });
    return;
  }

  if (!("speechSynthesis" in window) || !text.trim()) {
    // No TTS available — still surface the text as a subtitle briefly
    const prepared = prepareSpeakText(text);
    if (prepared && handlers.onSubtitle) {
      handlers.onSubtitle(prepared);
      window.setTimeout(() => {
        if (gen === speakGeneration) handlers.onSubtitle?.(null);
      }, Math.min(9000, 1800 + prepared.length * 55));
    }
    handlers.onEnd?.();
    return;
  }

  void speakBrowserChunks(text, gender, handlers, gen);
}

export function cancelSpeech() {
  stopAllSpeech();
}

if (typeof window !== "undefined" && "speechSynthesis" in window) {
  // Warm the voice list early so the first reply isn't stuck on a robotic default
  void ensureVoices();
  window.speechSynthesis.onvoiceschanged = () => {
    voicesReady = null;
    void ensureVoices();
  };
}
