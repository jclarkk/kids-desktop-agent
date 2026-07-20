import { useEffect, useRef, useState } from "react";
import { speakText } from "./speak";

type Props = {
  open: boolean;
  parentUnlocked: boolean;
  existingKids: number;
  onClose: () => void;
  onNeedParent: () => void;
  onSubmit: (payload: Record<string, unknown>) => void;
  message?: string | null;
  /** Prefer backend Kokoro; falls back to browser TTS. */
  speak?: (
    text: string,
    gender: string,
    options?: { level?: EnglishLevel; voiceId?: string }
  ) => void;
};

type StepId = "hello" | "name" | "friend" | "age" | "english" | "look" | "voice" | "done";
type EnglishLevel = "beginner" | "elementary" | "intermediate";

const STEPS: StepId[] = ["hello", "name", "friend", "age", "english", "look", "voice", "done"];

const FRIENDS = [
  { id: "rosie", label: "Rosie", blurb: "👑 Princess" },
  { id: "blaze", label: "Blaze", blurb: "🦸 Hero" },
  { id: "sparkle", label: "Sparkle", blurb: "🦄 Unicorn" },
  { id: "rex", label: "Rex", blurb: "🦖 Dino" },
  { id: "marina", label: "Marina", blurb: "🧜 Mermaid" },
  { id: "astro", label: "Astro", blurb: "🚀 Astronaut" },
  { id: "finn", label: "Finn", blurb: "🦜 Pirate" },
  { id: "flora", label: "Flora", blurb: "🧚 Fairy" },
  { id: "ember", label: "Ember", blurb: "🐉 Dragon" },
  { id: "sparky", label: "Sparky", blurb: "⭐ Star" },
  { id: "pixel", label: "Pixel", blurb: "🤖 Robot" },
  { id: "luna", label: "Luna", blurb: "🌙 Moon" },
];

const MIN_AGE = 2;
const MAX_AGE = 18;
const AGES = Array.from({ length: MAX_AGE - MIN_AGE + 1 }, (_, i) => MIN_AGE + i);

const AGE_WORDS: Record<string, number> = {
  two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16,
  seventeen: 17, eighteen: 18,
  // common mishearings from kid speech
  to: 2, too: 2, for: 4, free: 3, tree: 3, ate: 8,
};

/** Pull an age (2–18) out of a spoken phrase like "I am seven" or "7 years old". */
function parseSpokenAge(transcript: string): number | null {
  const text = transcript.toLowerCase();
  const digits = text.match(/\b(\d{1,2})\b/);
  if (digits) {
    const n = Number(digits[1]);
    return n >= MIN_AGE && n <= MAX_AGE ? n : null;
  }
  for (const token of text.split(/[^a-z]+/)) {
    const n = AGE_WORDS[token];
    if (n !== undefined) return n;
  }
  return null;
}

const ENGLISH_CHOICES: Array<{
  id: EnglishLevel | "unsure";
  emoji: string;
  title: string;
  sub: string;
  speak: string;
}> = [
  {
    id: "beginner",
    emoji: "🌱",
    title: "New words",
    sub: "Little / no English",
    speak: "New words. Very easy English.",
  },
  {
    id: "elementary",
    emoji: "📘",
    title: "Some English",
    sub: "Simple sentences",
    speak: "Some English. Simple sentences.",
  },
  {
    id: "intermediate",
    emoji: "🗣️",
    title: "More English",
    sub: "I can talk more",
    speak: "More English. Good job!",
  },
  {
    id: "unsure",
    emoji: "🤷",
    title: "Not sure",
    sub: "We start easy",
    speak: "Not sure. We start easy.",
  },
];

function coachLine(step: StepId, name: string, level: EnglishLevel): string {
  // Warm, inviting lines — still short for beginners; fuller for more English
  const basic = level === "beginner";
  switch (step) {
    case "hello":
      return basic
        ? "Hi friend! Tap the green button. We go slow."
        : "Hi friend! I am so happy you are here. Tap the big green button — we go one step at a time.";
    case "name":
      return basic
        ? "What is your name? A grown-up can help. Then tap Next."
        : "What is your name? A grown-up can help type it, then tap Next.";
    case "friend":
      return basic
        ? "Yay! Pick a friend. Tap one you like."
        : "Wonderful! Pick a friend to talk with — a princess, a hero, a dino, and more.";
    case "age":
      return basic
        ? "How old are you? Tap a number. Or press the mic and say it!"
        : "How old are you? Tap your age, or press the microphone and say it.";
    case "english":
      return basic
        ? "English time! Tap a picture. Not sure? Tap Not sure. We start easy."
        : "How much English do you know? Tap a picture. If you are not sure, tap Not sure — we start easy together.";
    case "look":
      return basic
        ? "Want a photo? Smile big! Or tap Skip. Both are okay."
        : "Optional photo for your friend. Smile, tap Take photo. Or Skip — that is fine too.";
    case "voice":
      return basic
        ? name
          ? `Hold the mic and say: Hi, I am ${name}! Or tap Skip.`
          : "Hold the mic and say Hi! Or tap Skip."
        : name
          ? `Hold the mic and say: Hi, I am ${name}! Or Skip if you prefer.`
          : "Hold the mic and say hello. Or Skip if you prefer.";
    case "done":
      return basic
        ? name
          ? `Yay ${name}! You did it. Tap Let's play!`
          : "Yay! You did it. Tap Let's play!"
        : name
          ? `Wonderful, ${name}! You are ready. Tap Let's play to meet your friend.`
          : "Wonderful! You are ready. Tap Let's play!";
  }
}

export function OnboardingWizard({
  open,
  parentUnlocked,
  existingKids,
  onClose,
  onNeedParent,
  onSubmit,
  message,
  speak,
}: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [age, setAge] = useState<number | null>(null);
  const [gender, setGender] = useState<"boy" | "girl" | "neutral">("neutral");
  const [avatar, setAvatar] = useState("sparky");
  // Default beginner until they choose (or tap Not sure)
  const [englishLevel, setEnglishLevel] = useState<EnglishLevel>("beginner");
  const [englishChoice, setEnglishChoice] = useState<EnglishLevel | "unsure" | null>(null);
  const [faceB64, setFaceB64] = useState<string | null>(null);
  const [voiceB64, setVoiceB64] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState<string | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordSecs, setRecordSecs] = useState(0);
  const [ageListening, setAgeListening] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordTimerRef = useRef<number | null>(null);
  const stepId = STEPS[step];

  // Warm coach voice: Kokoro af_heart via backend when available
  const say = (text: string) =>
    (speak || speakText)(text, "girl", {
      level: englishLevel,
      voiceId: "af_heart",
    });

  useEffect(() => {
    if (!open) return;
    if (existingKids > 0 && !parentUnlocked) onNeedParent();
  }, [open, existingKids, parentUnlocked, onNeedParent]);

  useEffect(() => {
    return () => {
      stopMedia();
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const line = coachLine(stepId, name.trim(), englishLevel);
    const t = window.setTimeout(() => say(line), 350);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, stepId]);

  useEffect(() => {
    if (!open || stepId !== "look") {
      stopCameraOnly();
      return;
    }
    void startCamera();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, stepId]);

  function stopCameraOnly() {
    streamRef.current?.getTracks().forEach((t) => {
      if (t.kind === "video") t.stop();
    });
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraReady(false);
  }

  function stopMedia() {
    if (recordTimerRef.current) window.clearInterval(recordTimerRef.current);
    mediaRecorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraReady(false);
    setRecording(false);
  }

  function replayCoach() {
    say(coachLine(stepId, name.trim(), englishLevel));
  }

  function goNext() {
    if (!canAdvance()) return;
    if (stepId === "english" && englishChoice == null) {
      setEnglishLevel("beginner");
      setEnglishChoice("unsure");
    }
    const cheers: Partial<Record<StepId, string>> = {
      name: englishLevel === "beginner" ? `Hi ${name.trim()}!` : `Nice to meet you, ${name.trim()}!`,
      friend: "Good!",
      age: `${age}!`,
      english: englishLevel === "beginner" ? "Easy English. Good." : "Okay!",
      look: faceB64 ? "Nice!" : "Okay!",
      voice: voiceB64 ? "Good!" : "Okay!",
    };
    if (cheers[stepId]) {
      setCelebrate(cheers[stepId] || null);
      say(cheers[stepId] || "");
      window.setTimeout(() => {
        setCelebrate(null);
        setStep((s) => Math.min(s + 1, STEPS.length - 1));
      }, 800);
    } else {
      setStep((s) => Math.min(s + 1, STEPS.length - 1));
    }
  }

  function goBack() {
    setCelebrate(null);
    setStep((s) => Math.max(0, s - 1));
  }

  function canAdvance(): boolean {
    if (stepId === "name") return name.trim().length >= 1;
    if (stepId === "age") return age != null;
    // english can always advance — default beginner if unsure/skipped
    return true;
  }

  function blockerHint(): string | null {
    if (stepId === "name" && !name.trim()) return "Name → Next";
    if (stepId === "age" && age == null) return "Tap or say your age";
    return null;
  }

  async function startCamera() {
    setCameraError(null);
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
      setCameraReady(true);
    } catch {
      setCameraError("Camera? Ask grown-up. Or Skip.");
      setCameraReady(false);
    }
  }

  function snapFace() {
    const video = videoRef.current;
    if (!video || !cameraReady) {
      setCameraError("Camera first. Then smile!");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 320;
    canvas.height = video.videoHeight || 240;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    setFaceB64(canvas.toDataURL("image/jpeg", 0.85));
    setCameraError(null);
    say("Nice!");
  }

  async function startVoiceHold() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const buf = await blob.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = "";
        bytes.forEach((b) => {
          binary += String.fromCharCode(b);
        });
        setVoiceB64(btoa(binary));
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setRecordSecs(0);
        if (recordTimerRef.current) window.clearInterval(recordTimerRef.current);
        say("Good!");
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setRecordSecs(0);
      recordTimerRef.current = window.setInterval(() => {
        setRecordSecs((s) => {
          if (s >= 3) {
            recorder.stop();
            return s;
          }
          return s + 1;
        });
      }, 1000);
      window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 3200);
    } catch {
      say("Mic? Ask grown-up. Or Skip.");
    }
  }

  function stopVoiceHold() {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  }

  function listenForAge() {
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor || ageListening) return;
    setAgeListening(true);
    const recog = new Ctor();
    recog.lang = "en-US";
    recog.interimResults = false;
    recog.continuous = false;
    recog.onresult = (event: SpeechRecognitionEvent) => {
      const text = event.results[0]?.[0]?.transcript || "";
      const parsed = parseSpokenAge(text);
      if (parsed != null) {
        setAge(parsed);
        say(`${parsed}!`);
      } else {
        say(englishLevel === "beginner" ? "Say a number. Like seven." : "Hmm, say a number — like seven.");
      }
    };
    recog.onerror = () => setAgeListening(false);
    recog.onend = () => setAgeListening(false);
    try {
      recog.start();
    } catch {
      setAgeListening(false);
    }
  }

  function pickEnglish(choice: EnglishLevel | "unsure") {
    const level: EnglishLevel = choice === "unsure" ? "beginner" : choice;
    setEnglishLevel(level);
    setEnglishChoice(choice);
    const item = ENGLISH_CHOICES.find((c) => c.id === choice);
    say(item?.speak || "Easy English.");
  }

  function finish() {
    stopMedia();
    const level = englishChoice == null ? "beginner" : englishLevel;
    onSubmit({
      name: name.trim() || "Friend",
      age: age ?? 6,
      preferred_gender: gender,
      preferred_avatar: avatar,
      english_level: level,
      daily_limit_minutes: (age ?? 6) <= 5 ? 45 : 60,
      magic_word: "",
      face_image_b64: faceB64,
      voice_audio_b64: voiceB64,
      voice_ext: "webm",
    });
  }

  if (!open) return null;

  if (existingKids > 0 && !parentUnlocked) {
    return (
      <div className="gate-panel onboard-panel">
        <h2>Grown-up</h2>
        <p className="coach-line">PIN please. Then we add a child.</p>
        <button type="button" className="guide-primary" onClick={onNeedParent}>
          Grown-up unlock
        </button>
        <button type="button" className="guide-secondary" onClick={onClose}>
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="gate-panel onboard-panel">
      <div className="onboard-progress" aria-hidden>
        {STEPS.map((id, i) => (
          <span key={id} className={i === step ? "dot active" : i < step ? "dot done" : "dot"} />
        ))}
      </div>

      <p className="onboard-step-label">
        {step + 1} / {STEPS.length}
      </p>

      <p className="coach-line" key={stepId}>
        {celebrate || coachLine(stepId, name.trim(), englishLevel)}
      </p>

      <button type="button" className="guide-secondary hear-again" onClick={replayCoach}>
        🔊 Again
      </button>

      {stepId === "hello" ? (
        <div className="onboard-body center">
          <div className="hello-bubble">👋</div>
          <p className="coach-sub">Slow. One step.</p>
        </div>
      ) : null}

      {stepId === "name" ? (
        <div className="onboard-body">
          <label className="big-label">
            Name
            <input
              className="big-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="…"
              autoFocus
            />
          </label>
          <p className="coach-sub">Grown-up can type.</p>
          <div className="big-choice-row">
            {(
              [
                ["boy", "Boy"],
                ["girl", "Girl"],
                ["neutral", "Me"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={gender === id ? "big-choice active" : "big-choice"}
                onClick={() => setGender(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {stepId === "friend" ? (
        <div className="onboard-body">
          <div className="friend-grid friend-grid-many">
            {FRIENDS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={avatar === f.id ? "friend-card active" : "friend-card"}
                onClick={() => {
                  setAvatar(f.id);
                  say(f.label);
                }}
              >
                <span className="friend-emoji">{f.blurb.split(" ")[0]}</span>
                <strong>{f.label}</strong>
                <small>{f.blurb.split(" ").slice(1).join(" ")}</small>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {stepId === "age" ? (
        <div className="onboard-body">
          <div className="age-grid">
            {AGES.map((n) => (
              <button
                key={n}
                type="button"
                className={age === n ? "age-btn active" : "age-btn"}
                onClick={() => {
                  setAge(n);
                  say(String(n));
                }}
              >
                {n}
              </button>
            ))}
          </div>
          {window.SpeechRecognition || window.webkitSpeechRecognition ? (
            <button
              type="button"
              className={ageListening ? "guide-secondary age-say listening" : "guide-secondary age-say"}
              onClick={listenForAge}
            >
              {ageListening ? "👂 Listening…" : "🎤 Say your age"}
            </button>
          ) : null}
        </div>
      ) : null}

      {stepId === "english" ? (
        <div className="onboard-body">
          <div className="friend-grid">
            {ENGLISH_CHOICES.map((c) => (
              <button
                key={c.id}
                type="button"
                className={englishChoice === c.id ? "friend-card active" : "friend-card"}
                onClick={() => pickEnglish(c.id)}
              >
                <span className="friend-emoji">{c.emoji}</span>
                <strong>{c.title}</strong>
                <small>{c.sub}</small>
              </button>
            ))}
          </div>
          <p className="coach-sub">Not sure → easy (🌱).</p>
        </div>
      ) : null}

      {stepId === "look" ? (
        <div className="onboard-body">
          <video ref={videoRef} className="gate-video" muted playsInline />
          {cameraError ? <p className="error">{cameraError}</p> : null}
          {faceB64 ? <img src={faceB64} alt="" className="who-face large" /> : null}
          <div className="big-choice-row">
            {!cameraReady ? (
              <button type="button" className="guide-primary" onClick={startCamera}>
                Camera
              </button>
            ) : (
              <button type="button" className="guide-primary" onClick={snapFace}>
                Photo
              </button>
            )}
            <button
              type="button"
              className="guide-secondary"
              onClick={() => {
                setFaceB64(null);
                goNext();
              }}
            >
              Skip
            </button>
          </div>
        </div>
      ) : null}

      {stepId === "voice" ? (
        <div className="onboard-body center">
          <button
            type="button"
            className={recording ? "record-orb active" : "record-orb"}
            onMouseDown={startVoiceHold}
            onMouseUp={stopVoiceHold}
            onMouseLeave={stopVoiceHold}
            onTouchStart={(e) => {
              e.preventDefault();
              void startVoiceHold();
            }}
            onTouchEnd={stopVoiceHold}
          >
            {recording ? `${Math.max(0, 3 - recordSecs)}` : "🎤"}
          </button>
          <p className="coach-sub">
            {recording ? "Hi!" : voiceB64 ? "Good! Next." : "Hold → say Hi"}
          </p>
          <button
            type="button"
            className="guide-secondary"
            onClick={() => {
              setVoiceB64(null);
              goNext();
            }}
          >
            Skip
          </button>
        </div>
      ) : null}

      {stepId === "done" ? (
        <div className="onboard-body center">
          <div className="hello-bubble">🎉</div>
          <p className="coach-sub">Hi {name.trim() || "friend"}!</p>
          {message ? <p className="error">{message}</p> : null}
          <button type="button" className="guide-primary" onClick={finish}>
            Let's play!
          </button>
        </div>
      ) : null}

      {stepId !== "done" ? (
        <div className="onboard-nav">
          {step > 0 ? (
            <button type="button" className="guide-secondary" onClick={goBack}>
              Back
            </button>
          ) : (
            <button type="button" className="guide-secondary" onClick={onClose}>
              Close
            </button>
          )}
          <button
            type="button"
            className="guide-primary"
            disabled={!canAdvance()}
            onClick={goNext}
          >
            {stepId === "hello" ? "Go!" : stepId === "english" && englishChoice == null ? "Start easy →" : "Next"}
          </button>
        </div>
      ) : null}

      {blockerHint() ? <p className="blocker-hint">{blockerHint()}</p> : null}

      <p className="parent-help">Grown-up help OK. You are great.</p>
    </div>
  );
}
