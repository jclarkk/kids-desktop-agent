import { useEffect, useRef, useState } from "react";
import { AgentSocket, type AgentState, type AvatarState } from "./agentSocket";
import { AvatarFace } from "./AvatarFace";
import { createBackendSpeaker } from "./backendSpeak";
import { ComputerUseBanner } from "./ComputerUseBanner";
import { pickNudgeLine, pickSuggestions, type EnglishLevel } from "./curiosity";
import { KidMenu } from "./KidMenu";
import { OnboardingWizard } from "./OnboardingWizard";
import { ParentPanel, type ParentSettings } from "./ParentPanel";
import { ParentSetupWizard } from "./ParentSetupWizard";
import { speakText } from "./speak";
import { keyLabel, usePushToTalk } from "./usePushToTalk";
import { WhoIsPlaying } from "./WhoIsPlaying";

declare global {
  interface Window {
    kda?: {
      minimize: () => Promise<void>;
      close: () => Promise<void>;
      resize: (width: number, height: number) => Promise<void>;
      backendStatus: () => Promise<{ running?: boolean; lastError?: string | null }>;
      restartBackend: () => Promise<{ running?: boolean; lastError?: string | null }>;
      onBackendStatus: (
        handler: (status: { running?: boolean; lastError?: string | null }) => void
      ) => () => void;
    };
  }
}

const KID_WINDOW = { width: 320, height: 640 };
const PARENT_WINDOW = { width: 760, height: 680 };

// First curiosity nudge after ~45s of quiet; later ones spaced out more.
const NUDGE_FIRST_MS = 45_000;
const NUDGE_REPEAT_MS = 180_000;

type Subtitle = { speaker: "you" | "avatar"; text: string };

export function App() {
  const [conn, setConn] = useState<"connecting" | "open" | "closed">("connecting");
  const [agent, setAgent] = useState<AgentState>({});
  const [avatarState, setAvatarState] = useState<AvatarState>("idle");
  const [subtitle, setSubtitle] = useState<Subtitle | null>(null);
  const [draft, setDraft] = useState("");
  const [textOpen, setTextOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [parentOpen, setParentOpen] = useState(false);
  const [parentUnlocked, setParentUnlocked] = useState(false);
  const [parentError, setParentError] = useState<string | null>(null);
  const [parentSettings, setParentSettings] = useState<ParentSettings | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<
    Array<{ id: string; label: string; ollama: string; fit: string; notes?: string }>
  >([]);
  const [hardware, setHardware] = useState<{
    vram_gb?: number | null;
    gpu_name?: string | null;
    ollama_ok?: boolean;
    ollama_models?: string[];
  } | null>(null);
  const [budget, setBudget] = useState<{
    spent_usd?: number;
    limit_usd?: number;
    remaining_usd?: number;
  } | null>(null);
  const [gender, setGender] = useState<"boy" | "girl" | "neutral">("neutral");
  const [characterId, setCharacterId] = useState("sparky");
  const [packId, setPackId] = useState("starter");
  const [showGate, setShowGate] = useState(false);
  const [gateDismissed, setGateDismissed] = useState(false);
  const [showOnboard, setShowOnboard] = useState(false);
  const [gateMessage, setGateMessage] = useState<string | null>(null);
  const [onboardMessage, setOnboardMessage] = useState<string | null>(null);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);
  const [cuMessage, setCuMessage] = useState<string | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const nudgedOnceRef = useRef(false);
  const socketRef = useRef<AgentSocket | null>(null);
  const speakerRef = useRef(createBackendSpeaker((payload) => socketRef.current?.send(payload)));
  const subtitleClearRef = useRef<number | null>(null);
  const genderRef = useRef(gender);
  genderRef.current = gender;
  const agentRef = useRef(agent);
  agentRef.current = agent;

  function showSubtitle(next: Subtitle | null, lingerMs = 0) {
    if (subtitleClearRef.current) {
      window.clearTimeout(subtitleClearRef.current);
      subtitleClearRef.current = null;
    }
    if (next === null && lingerMs > 0) {
      subtitleClearRef.current = window.setTimeout(() => setSubtitle(null), lingerMs);
      return;
    }
    setSubtitle(next);
  }

  useEffect(() => {
    // Unlock HTMLAudioElement autoplay after the first tap (Kokoro WAV needs this;
    // speechSynthesis alone does not).
    const unlock = () => {
      try {
        const a = new Audio(
          "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA="
        );
        void a.play().then(() => {
          a.pause();
          a.src = "";
        });
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("pointerdown", unlock, { once: true });
    return () => window.removeEventListener("pointerdown", unlock);
  }, []);

  useEffect(() => {
    const socket = new AgentSocket(
      (msg) => {
        if (msg.type === "state") {
          const state = msg as AgentState;
          setAgent(state);
          if (state.avatar?.gender) setGender(state.avatar.gender);
          if (state.avatar?.character_id) setCharacterId(state.avatar.character_id);
          if (state.avatar?.pack_id) setPackId(state.avatar.pack_id);
          if (Array.isArray(state.local_catalog)) setCatalog(state.local_catalog);
          if (state.hardware) setHardware(state.hardware);
          if (state.budget) setBudget(state.budget);
          if (state.needs_who_is_playing) setShowGate(true);
          if (state.active_kid_id) {
            setShowGate(false);
            setGateDismissed(false);
          }
          if (!state.kids?.length) setShowOnboard(true);
        }
        if (msg.type === "avatar_state" && typeof msg.state === "string") {
          setAvatarState(msg.state as AvatarState);
        }
        if (msg.type === "assistant_reply") {
          const text = String(msg.text || "");
          const replyGender = String(msg.gender || genderRef.current);
          if (msg.budget) setBudget(msg.budget as typeof budget);
          if (msg.usage) {
            setAgent((prev) => ({ ...prev, usage: msg.usage as AgentState["usage"] }));
          }
          speakText(text, replyGender, {
            level:
              agentRef.current.kids?.find((k) => k.id === agentRef.current.active_kid_id)
                ?.english_level || "beginner",
            voiceId: String(msg.voice_id || agentRef.current.voice_id || ""),
            audioUrl:
              msg.speech &&
              typeof msg.speech === "object" &&
              (msg.speech as { mime?: string; b64?: string }).b64
                ? `data:${(msg.speech as { mime?: string }).mime || "audio/wav"};base64,${
                    (msg.speech as { b64: string }).b64
                  }`
                : null,
            onStart: () => setAvatarState("speaking"),
            onBoundary: () => setAvatarState("speaking"),
            onEnd: () => setAvatarState("idle"),
            onSubtitle: (sentence) => {
              if (sentence) showSubtitle({ speaker: "avatar", text: sentence });
              else showSubtitle(null, 2500);
            },
          });
        }
        if (msg.type === "tts_result") {
          speakerRef.current.handleResult(msg);
        }
        if (msg.type === "stt_result") {
          if (msg.ok && msg.text) {
            sendText(String(msg.text));
          } else {
            showSubtitle({ speaker: "avatar", text: "I couldn't hear that. Try again?" }, 2500);
          }
        }
        if (msg.type === "identify_result") {
          if (msg.ok) {
            setGateMessage(null);
            setShowGate(false);
            setGateDismissed(false);
          } else {
            setGateMessage(String(msg.error || "Hmm, let's try again!"));
          }
        }
        if (msg.type === "onboard_kid_result") {
          if (msg.ok) {
            setShowOnboard(false);
            setShowGate(false);
            setOnboardMessage(null);
          } else {
            setOnboardMessage(String(msg.error || "Onboarding failed"));
          }
        }
        if (msg.type === "parent_setup_result") {
          if (msg.ok) {
            setSetupMessage(null);
            if (msg.settings) setParentSettings(msg.settings as ParentSettings);
            setParentUnlocked(true);
          } else {
            setSetupMessage(String(msg.error || "Parent setup failed"));
          }
        }
        if (msg.type === "parent_unlock_result") {
          const ok = Boolean(msg.ok);
          setParentUnlocked(ok);
          setParentError(ok ? null : "Incorrect PIN");
          if (ok && msg.settings) {
            setParentSettings(msg.settings as ParentSettings);
          }
          if (ok && Array.isArray(msg.local_catalog)) setCatalog(msg.local_catalog as typeof catalog);
          if (ok && msg.hardware) setHardware(msg.hardware as typeof hardware);
          if (ok && msg.budget) setBudget(msg.budget as typeof budget);
        }
        if (msg.type === "parent_save_result") {
          if (msg.ok) {
            setSaveMessage("Saved to config.local.json");
            if (msg.settings) setParentSettings(msg.settings as ParentSettings);
            setParentError(null);
          } else {
            setSaveMessage(null);
            setParentError(String(msg.error || "Save failed"));
          }
        }
        if (msg.type === "privacy_clear_result") {
          if (msg.ok) {
            setSaveMessage("Local data cleared.");
            setParentError(null);
          } else {
            setSaveMessage(null);
            setParentError(String(msg.error || "Could not clear local data"));
          }
        }
        if (msg.type === "timer_event") {
          const label = String(msg.label || "Timer");
          const message =
            msg.event === "done"
              ? String(msg.message || `${label} is done!`)
              : `${label} started.`;
          showSubtitle({ speaker: "avatar", text: message }, msg.event === "done" ? 5000 : 2500);
          if (msg.event === "done") {
            void speakerRef.current.speak(message, genderRef.current, {
              level:
                agentRef.current.kids?.find((k) => k.id === agentRef.current.active_kid_id)
                  ?.english_level || "beginner",
              voiceId: String(agentRef.current.voice_id || ""),
            });
          }
        }
        if (msg.type === "computer_use_event") {
          setCuMessage(String(msg.message || ""));
          if (msg.event === "stopped" || msg.event === "denied") {
            window.setTimeout(() => setCuMessage(null), 2500);
          }
        }
      },
      setConn
    );
    socketRef.current = socket;
    socket.connect();
    return () => socket.close();
  }, []);

  useEffect(() => {
    void window.kda?.backendStatus?.().then((status) => {
      setBackendError(status?.lastError || null);
    });
    return window.kda?.onBackendStatus?.((status) => {
      setBackendError(status?.lastError || null);
    });
  }, []);

  const overLimit = Boolean(agent.usage?.over_limit);
  const setupOpen = Boolean(agent.needs_parent_setup);
  const gateOpen = !gateDismissed && (showGate || Boolean(agent.needs_who_is_playing));
  const overlayOpen = setupOpen || gateOpen || showOnboard || parentOpen || menuOpen;

  function sendText(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSuggestions(null);
    showSubtitle({ speaker: "you", text: trimmed });
    socketRef.current?.send({ type: "user_text", text: trimmed });
    setDraft("");
  }

  const ptt = usePushToTalk({
    enabled: !overLimit && !overlayOpen,
    onText: sendText,
    useBackendStt: agent.speech?.stt === "faster_whisper",
    onAudio: (audioB64, ext) =>
      socketRef.current?.send({
        type: "stt_transcribe",
        request_id: `stt_${Date.now()}`,
        audio_b64: audioB64,
        ext,
      }),
    onListenStart: () => {
      setSuggestions(null);
      setAvatarState("listening");
      socketRef.current?.send({ type: "avatar_state", state: "listening" });
    },
    onListenEnd: () => {
      setAvatarState((prev) => (prev === "listening" ? "idle" : prev));
    },
  });

  // Curiosity nudge: after a quiet stretch, invite the kid to ask anything
  // and offer tappable question ideas. Timer restarts whenever activity
  // (speaking/listening/overlays/games) interrupts the idle state.
  const nudgeEligible =
    conn === "open" &&
    !overlayOpen &&
    !overLimit &&
    !agent.game &&
    avatarState === "idle" &&
    !ptt.listening &&
    Boolean(agent.active_kid_id);

  useEffect(() => {
    if (!nudgeEligible || suggestions) return;
    const delay = nudgedOnceRef.current ? NUDGE_REPEAT_MS : NUDGE_FIRST_MS;
    const timer = window.setTimeout(() => {
      nudgedOnceRef.current = true;
      const level = (agentRef.current.kids?.find(
        (k) => k.id === agentRef.current.active_kid_id
      )?.english_level || "beginner") as EnglishLevel;
      setSuggestions(pickSuggestions(level));
      void speakerRef.current.speak(pickNudgeLine(level), genderRef.current, {
        level,
        voiceId: String(agentRef.current.voice_id || ""),
        onStart: () => setAvatarState("speaking"),
        onEnd: () => setAvatarState("idle"),
        onSubtitle: (sentence) => {
          if (sentence) showSubtitle({ speaker: "avatar", text: sentence });
          else showSubtitle(null, 2500);
        },
      });
    }, delay);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nudgeEligible, suggestions]);

  // Grow the window for parent settings; shrink back for the kid view
  useEffect(() => {
    if (parentOpen) {
      void window.kda?.resize(PARENT_WINDOW.width, PARENT_WINDOW.height);
    } else {
      void window.kda?.resize(KID_WINDOW.width, KID_WINDOW.height);
    }
  }, [parentOpen]);

  // Games are answered by typing too — open the drawer during a game
  useEffect(() => {
    if (agent.game) setTextOpen(true);
  }, [agent.game]);

  function applyAvatar(next: {
    pack_id: string;
    character_id: string;
    gender: "boy" | "girl" | "neutral";
  }) {
    setPackId(next.pack_id);
    setCharacterId(next.character_id);
    setGender(next.gender);
    socketRef.current?.send({
      type: "set_avatar",
      pack_id: next.pack_id,
      character_id: next.character_id,
      gender: next.gender,
    });
  }

  const connTitle =
    conn !== "open"
      ? "Backend offline — start python -m kids_agent"
      : overLimit
        ? "Time limit reached for today"
        : `Connected · ${agent.ai_mode || "cloud"}`;

  return (
    <div className="shell" onContextMenu={(e) => e.preventDefault()}>
      <div className="titlebar">
        <span className="drag">
          <span
            className={`conn-dot ${conn === "open" ? "ok" : conn === "closed" ? "bad" : ""}`}
            title={connTitle}
          />
          Kids Desktop Agent
        </span>
        <div className="window-actions">
          <button
            type="button"
            className="icon-btn"
            title="Minimize"
            onClick={() => window.kda?.minimize()}
          >
            —
          </button>
          <button
            type="button"
            className="icon-btn"
            title="Close"
            onClick={() => window.kda?.close()}
          >
            ✕
          </button>
        </div>
      </div>

      <ComputerUseBanner
        status={agent.computer_use}
        message={cuMessage}
        onStop={() => socketRef.current?.send({ type: "computer_use_stop" })}
        onApprove={(pin) => socketRef.current?.send({ type: "computer_use_approve", pin })}
        onDeny={() => socketRef.current?.send({ type: "computer_use_deny" })}
        onStartSession={(pin) =>
          socketRef.current?.send({ type: "computer_use_start_session", pin })
        }
      />

      <div className="stage">
        <AvatarFace
          characterId={characterId}
          state={ptt.listening ? "listening" : avatarState}
          onPressStart={ptt.start}
          onPressEnd={ptt.stop}
        />

        <div className="subtitle-area" aria-live="polite">
          {overLimit ? (
            <p className="subtitle">🌙 All done for today! See you tomorrow.</p>
          ) : backendError ? (
            <p className="subtitle">
              <span className="speaker">App</span>
              Backend problem. Please restart the app.
            </p>
          ) : subtitle ? (
            <p className={subtitle.speaker === "you" ? "subtitle you" : "subtitle"}>
              <span className="speaker">{subtitle.speaker === "you" ? "You" : "Friend"}</span>
              {subtitle.text}
            </p>
          ) : null}
        </div>

        {suggestions && !overLimit && !overlayOpen ? (
          <div className="suggest-col" aria-label="Question ideas">
            {suggestions.map((q) => (
              <button key={q} type="button" className="suggest-chip" onClick={() => sendText(q)}>
                💬 {q}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className={`text-drawer ${textOpen ? "open" : ""}`}>
        <form
          className="text-row"
          onSubmit={(e) => {
            e.preventDefault();
            sendText(draft);
          }}
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={agent.game ? "Your answer…" : "Type here…"}
            disabled={overLimit}
          />
          <button type="submit" disabled={overLimit}>
            Send
          </button>
        </form>
      </div>

      <div className="controls">
        <button
          type="button"
          className={`round-btn small ${textOpen ? "active" : ""}`}
          title="Type instead of talking"
          aria-label="Toggle keyboard"
          onClick={() => setTextOpen((v) => !v)}
        >
          ⌨
        </button>
        <button
          type="button"
          className={`round-btn ptt-btn ${ptt.listening ? "listening" : ""}`}
          title="Hold to talk"
          aria-label="Hold to talk"
          disabled={overLimit}
          onMouseDown={ptt.start}
          onMouseUp={ptt.stop}
          onMouseLeave={ptt.stop}
          onTouchStart={(e) => {
            e.preventDefault();
            ptt.start();
          }}
          onTouchEnd={ptt.stop}
        >
          🎤
        </button>
        <button
          type="button"
          className="round-btn small"
          title="Menu"
          aria-label="Open menu"
          onClick={() => setMenuOpen(true)}
        >
          ☰
        </button>
      </div>
      <p className="ptt-hint">
        Hold the button or <kbd>{keyLabel(ptt.pttKey)}</kbd> to talk
      </p>

      <ParentSetupWizard
        open={setupOpen}
        message={setupMessage}
        onSubmit={(payload) => socketRef.current?.send({ type: "parent_setup", ...payload })}
      />

      <KidMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        packs={agent.avatar_packs || []}
        packId={packId}
        characterId={characterId}
        gender={gender}
        onAvatarChange={applyAvatar}
        games={agent.games_available || []}
        activeGame={agent.game || null}
        onStartGame={(kind) => socketRef.current?.send({ type: "start_game", kind })}
        onCancelGame={() => socketRef.current?.send({ type: "cancel_game" })}
        showKidSwitch={(agent.kids || []).length > 0}
        onSwitchKid={() => {
          socketRef.current?.send({ type: "clear_kid" });
          setGateDismissed(false);
          setShowGate(true);
        }}
        onOpenParent={() => {
          setMenuOpen(false);
          setParentOpen(true);
        }}
        pttKey={ptt.pttKey}
        onSetPttKey={ptt.setPttKey}
        usage={agent.usage}
      />

      <WhoIsPlaying
        open={gateOpen && !showOnboard && !parentOpen}
        kids={agent.kids || []}
        identity={agent.identity}
        message={gateMessage}
        speak={speakerRef.current.speak}
        onClose={() => {
          setShowGate(false);
          setGateDismissed(true);
        }}
        onSelect={(kidId) => {
          socketRef.current?.send({ type: "set_kid", kid_id: kidId });
          setShowGate(false);
        }}
        onIdentifyVoice={(transcript) =>
          socketRef.current?.send({ type: "identify_voice", transcript })
        }
        onIdentifyFace={(imageB64) =>
          socketRef.current?.send({ type: "identify_face", image_b64: imageB64 })
        }
        onStartOnboarding={() => setShowOnboard(true)}
      />

      <OnboardingWizard
        open={showOnboard}
        parentUnlocked={parentUnlocked}
        existingKids={(agent.kids || []).length}
        message={onboardMessage}
        speak={speakerRef.current.speak}
        onClose={() => setShowOnboard(false)}
        onNeedParent={() => {
          setShowOnboard(false);
          setParentOpen(true);
        }}
        onSubmit={(payload) => socketRef.current?.send({ type: "onboard_kid", ...payload })}
      />

      <ParentPanel
        open={parentOpen}
        onClose={() => {
          setParentOpen(false);
          setParentUnlocked(false);
          setParentError(null);
          setSaveMessage(null);
        }}
        onUnlock={(pin) => socketRef.current?.send({ type: "parent_unlock", pin })}
        unlocked={parentUnlocked}
        error={parentError}
        settings={parentSettings}
        saveMessage={saveMessage}
        onSave={(patch) => socketRef.current?.send({ type: "parent_save", patch })}
        catalog={catalog}
        hardware={hardware}
        budget={budget}
        onRefreshHardware={() => socketRef.current?.send({ type: "refresh_hardware" })}
        onPrivacyClear={(target) => socketRef.current?.send({ type: "privacy_clear", target })}
        onAddKid={() => {
          setParentOpen(false);
          setShowOnboard(true);
        }}
      />
    </div>
  );
}
