import { speakText, type SpeakOptions } from "./speak";

export type SpeechPayload = {
  mime?: string;
  b64?: string;
  voice?: string;
};

type Pending = {
  id: string;
  resolve: (speech: SpeechPayload | null) => void;
  timer: number;
};

/**
 * Request Kokoro (or whatever the backend has) for coach/onboarding lines.
 * Falls back to browser TTS if the backend has no neural voice ready,
 * or if synthesis is slow / blocked.
 */
export function createBackendSpeaker(send: (payload: Record<string, unknown>) => void) {
  const pending = new Map<string, Pending>();
  let seq = 0;
  let speakGen = 0;

  function rejectAll() {
    for (const entry of pending.values()) {
      window.clearTimeout(entry.timer);
      entry.resolve(null);
    }
    pending.clear();
  }

  function handleResult(msg: Record<string, unknown>) {
    const id = String(msg.request_id || "");
    const entry = id ? pending.get(id) : undefined;
    const target = entry || pending.values().next().value;
    if (!target) return;
    pending.delete(target.id);
    window.clearTimeout(target.timer);
    const speech =
      msg.ok && msg.speech && typeof msg.speech === "object"
        ? (msg.speech as SpeechPayload)
        : null;
    target.resolve(speech?.b64 ? speech : null);
  }

  async function speak(text: string, gender: string, options: SpeakOptions = {}) {
    const trimmed = text.trim();
    if (!trimmed) return;

    // Newer coach lines cancel older in-flight synthesis so we don't play
    // a stale "hello" after the kid already moved on.
    rejectAll();
    const gen = ++speakGen;
    const id = `tts_${seq++}_${Date.now()}`;

    const speech = await new Promise<SpeechPayload | null>((resolve) => {
      const timer = window.setTimeout(() => {
        pending.delete(id);
        resolve(null);
      }, 3_000);
      pending.set(id, { id, resolve, timer });
      try {
        send({
          type: "tts_synthesize",
          request_id: id,
          text: trimmed,
          gender,
          level: options.level || "beginner",
          voice_id: options.voiceId || undefined,
        });
      } catch {
        window.clearTimeout(timer);
        pending.delete(id);
        resolve(null);
      }
    });

    if (gen !== speakGen) return;

    const audioUrl =
      speech?.b64 != null
        ? `data:${speech.mime || "audio/wav"};base64,${speech.b64}`
        : null;

    speakText(trimmed, gender, { ...options, audioUrl });
  }

  return { speak, handleResult };
}

export type BackendSpeaker = ReturnType<typeof createBackendSpeaker>;
