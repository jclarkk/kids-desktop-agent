import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "kda_ptt_key";
export const DEFAULT_PTT_KEY = "Space";

/** Human-friendly label for a KeyboardEvent.code. */
export function keyLabel(code: string): string {
  if (code === "Space") return "Space";
  if (code.startsWith("Key")) return code.slice(3);
  if (code.startsWith("Digit")) return code.slice(5);
  if (code.startsWith("Numpad")) return `Num ${code.slice(6)}`;
  if (code.startsWith("Arrow")) return code.slice(5) + " arrow";
  return code;
}

export function loadPttKey(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || DEFAULT_PTT_KEY;
  } catch {
    return DEFAULT_PTT_KEY;
  }
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

type Options = {
  /** Disable listening entirely (e.g. daily limit reached, overlay open). */
  enabled: boolean;
  onText: (text: string) => void;
  onAudio?: (audioB64: string, ext: string) => void;
  useBackendStt?: boolean;
  onListenStart?: () => void;
  onListenEnd?: () => void;
};

/**
 * Shared hold-to-talk driver for the PTT button, the avatar, and the
 * kid-definable keyboard shortcut. One speech-recognition session at a time.
 */
export function usePushToTalk({
  enabled,
  onText,
  onAudio,
  useBackendStt = false,
  onListenStart,
  onListenEnd,
}: Options) {
  const [listening, setListening] = useState(false);
  const [pttKey, setPttKeyState] = useState<string>(() => loadPttKey());
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const keyHeldRef = useRef(false);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const onTextRef = useRef(onText);
  onTextRef.current = onText;
  const onAudioRef = useRef(onAudio);
  onAudioRef.current = onAudio;
  const useBackendSttRef = useRef(useBackendStt);
  useBackendSttRef.current = useBackendStt;
  const onListenStartRef = useRef(onListenStart);
  onListenStartRef.current = onListenStart;
  const onListenEndRef = useRef(onListenEnd);
  onListenEndRef.current = onListenEnd;

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    setListening(false);
    onListenEndRef.current?.();
  }, []);

  const start = useCallback(() => {
    if (!enabledRef.current || recognitionRef.current) return;
    if (useBackendSttRef.current && onAudioRef.current && navigator.mediaDevices?.getUserMedia) {
      setListening(true);
      onListenStartRef.current?.();
      void navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((stream) => {
          streamRef.current = stream;
          chunksRef.current = [];
          const recorder = new MediaRecorder(stream);
          recorder.ondataavailable = (event) => {
            if (event.data.size) chunksRef.current.push(event.data);
          };
          recorder.onstop = async () => {
            const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
            const buf = await blob.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = "";
            bytes.forEach((b) => {
              binary += String.fromCharCode(b);
            });
            const ext = (recorder.mimeType || "audio/webm").includes("ogg") ? "ogg" : "webm";
            onAudioRef.current?.(btoa(binary), ext);
            stream.getTracks().forEach((track) => track.stop());
            recorderRef.current = null;
            streamRef.current = null;
            setListening(false);
            onListenEndRef.current?.();
          };
          recorderRef.current = recorder;
          recorder.start();
        })
        .catch(() => {
          setListening(false);
          onListenEndRef.current?.();
        });
      return;
    }
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    setListening(true);
    onListenStartRef.current?.();
    if (!Ctor) return; // Visual feedback only; text box is the fallback
    const recog = new Ctor();
    recog.lang = "en-US";
    recog.interimResults = false;
    recog.continuous = false;
    recog.onresult = (event: SpeechRecognitionEvent) => {
      const text = event.results[0]?.[0]?.transcript || "";
      if (text) onTextRef.current(text);
    };
    recog.onerror = () => {
      recognitionRef.current = null;
      setListening(false);
      onListenEndRef.current?.();
    };
    recog.onend = () => {
      recognitionRef.current = null;
      setListening(false);
      onListenEndRef.current?.();
    };
    recognitionRef.current = recog;
    recog.start();
  }, []);

  const setPttKey = useCallback((code: string) => {
    setPttKeyState(code);
    try {
      window.localStorage.setItem(STORAGE_KEY, code);
    } catch {
      /* device preference only */
    }
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.code !== pttKey || e.repeat || keyHeldRef.current) return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      keyHeldRef.current = true;
      start();
    }
    function onKeyUp(e: KeyboardEvent) {
      if (e.code !== pttKey || !keyHeldRef.current) return;
      keyHeldRef.current = false;
      stop();
    }
    function onBlur() {
      if (keyHeldRef.current) {
        keyHeldRef.current = false;
        stop();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, [pttKey, start, stop]);

  return { listening, start, stop, pttKey, setPttKey };
}
