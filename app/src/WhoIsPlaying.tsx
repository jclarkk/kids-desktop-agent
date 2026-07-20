import { useEffect, useRef, useState } from "react";
import { speakText } from "./speak";

export type KidCard = {
  id: string;
  name: string;
  age: number;
  face_preview?: string;
  voice_enrolled?: boolean;
  face_enrolled?: boolean;
};

type IdentitySettings = {
  require_who_is_playing?: boolean;
  voice_name_match?: boolean;
  face_match?: boolean;
  allow_tap_select?: boolean;
};

type Props = {
  open: boolean;
  kids: KidCard[];
  identity?: IdentitySettings | null;
  message?: string | null;
  onClose: () => void;
  onSelect: (kidId: string) => void;
  onIdentifyVoice: (transcript: string) => void;
  onIdentifyFace: (imageB64: string) => void;
  onStartOnboarding: () => void;
  /** Prefer backend Kokoro; falls back to browser TTS. */
  speak?: (
    text: string,
    gender: string,
    options?: { level?: "beginner"; voiceId?: string }
  ) => void;
};

export function WhoIsPlaying({
  open,
  kids,
  identity,
  message,
  onClose,
  onSelect,
  onIdentifyVoice,
  onIdentifyFace,
  onStartOnboarding,
  speak,
}: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const line =
      kids.length > 1
        ? "Who is playing? Tap your name. A grown-up can help."
        : kids.length === 1
          ? `Hi! Is that you, ${kids[0].name}? Tap your name.`
          : "Hi friend! Tap I'm new, and we will set you up together.";
    const say = speak || speakText;
    const t = window.setTimeout(
      () => say(line, "girl", { level: "beginner", voiceId: "af_heart" }),
      400
    );
    return () => window.clearTimeout(t);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) stopCamera();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
    } catch {
      setCameraOn(false);
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraOn(false);
  }

  function captureFrame(): string | null {
    const video = videoRef.current;
    if (!video) return null;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 320;
    canvas.height = video.videoHeight || 240;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85);
  }

  function listenForName() {
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) {
      onIdentifyVoice("");
      return;
    }
    setBusy(true);
    const recog = new Ctor();
    recog.lang = "en-US";
    recog.interimResults = false;
    recog.onresult = (event: SpeechRecognitionEvent) => {
      const text = event.results[0]?.[0]?.transcript || "";
      onIdentifyVoice(text);
      setBusy(false);
    };
    recog.onerror = () => setBusy(false);
    recog.onend = () => setBusy(false);
    recog.start();
  }

  return (
    <div className="overlay" style={{ zIndex: 30 }}>
      <div className="modal" role="dialog" aria-label="Who is playing">
        <div className="modal-header">
          <h2>Who is playing?</h2>
          <button
            type="button"
            className="close-x"
            aria-label="Close"
            onClick={() => {
              stopCamera();
              onClose();
            }}
          >
            ✕
          </button>
        </div>

        <p className="coach-sub">Tap your name — a grown-up can help.</p>
        {message ? <p className="error">{message}</p> : null}

        {identity?.allow_tap_select !== false && kids.length > 0 ? (
          <div className="who-grid">
            {kids.map((kid) => (
              <button
                key={kid.id}
                type="button"
                className="who-card"
                onClick={() => {
                  stopCamera();
                  onSelect(kid.id);
                }}
              >
                {kid.face_preview ? (
                  <img src={kid.face_preview} alt="" className="who-face" />
                ) : (
                  <div className="who-face placeholder">{kid.name.slice(0, 1)}</div>
                )}
                <span>
                  {kid.name}
                  <small>age {kid.age}</small>
                </span>
              </button>
            ))}
          </div>
        ) : null}

        {cameraOn ? <video ref={videoRef} className="gate-video" muted playsInline /> : null}

        <div className="gate-actions">
          {identity?.voice_name_match !== false && kids.length > 0 ? (
            <button type="button" className="chip" disabled={busy} onClick={listenForName}>
              {busy ? "Listening…" : "🎤 Say my name"}
            </button>
          ) : null}
          {identity?.face_match !== false && kids.length > 0 ? (
            cameraOn ? (
              <>
                <button
                  type="button"
                  className="chip active"
                  onClick={() => {
                    const img = captureFrame();
                    if (img) onIdentifyFace(img);
                  }}
                >
                  It's me!
                </button>
                <button type="button" className="chip" onClick={stopCamera}>
                  Stop camera
                </button>
              </>
            ) : (
              <button type="button" className="chip" onClick={startCamera}>
                📷 Use camera
              </button>
            )
          ) : null}
          <button type="button" className="chip" onClick={onStartOnboarding}>
            ✨ I'm new
          </button>
        </div>
      </div>
    </div>
  );
}
