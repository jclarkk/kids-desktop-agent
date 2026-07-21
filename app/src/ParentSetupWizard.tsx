import { useEffect, useState } from "react";

export type SetupPayload = {
  pin: string;
  ai_mode: "cloud" | "local" | "hybrid";
  api_key?: string;
  provider?: string;
  base_url?: string;
  chat_model?: string;
  daily_budget_usd?: number;
  llm_model?: string;
  ollama_base_url?: string;
  daily_limit_minutes: number;
};

type Hardware = {
  vram_gb?: number | null;
  gpu_name?: string | null;
  ollama_ok?: boolean;
  ollama_models?: string[];
};

type CatalogItem = {
  id: string;
  label: string;
  ollama: string;
  fit: string;
  notes?: string;
  vision?: boolean;
  tools?: string;
  selected_default?: boolean;
  use_case?: string;
};

function looksLikeVisionModel(name: string): boolean {
  const raw = name.trim().toLowerCase();
  if (!raw) return false;
  if (raw.startsWith("qwen3.5") || raw.startsWith("gemma4") || raw.includes("gemma3")) {
    return true;
  }
  return /(?:^|[:/\-_])(?:vl|vision|llava|moondream|minicpm-v|bakllava)(?:$|[:/\-_\d])/.test(raw);
}

type Props = {
  open: boolean;
  message?: string | null;
  hardware?: Hardware | null;
  catalog?: CatalogItem[];
  onRefreshHardware?: () => void;
  onSubmit: (payload: SetupPayload) => void;
};

type StepId = "welcome" | "pin" | "mode" | "cloud" | "local" | "limits" | "ready";

const PROVIDERS = [
  {
    id: "openrouter",
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "google/gemini-2.5-flash",
    keyHint: "or-… (from openrouter.ai/keys)",
    helpUrl: "https://openrouter.ai/keys",
  },
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    keyHint: "sk-…",
    helpUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "gemini",
    label: "Gemini (OpenAI-compatible)",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    model: "gemini-2.5-flash",
    keyHint: "Google AI Studio key",
    helpUrl: "https://aistudio.google.com/apikey",
  },
] as const;

const OLLAMA_URL = "https://ollama.com/download";

function openLink(url: string) {
  if (window.kda?.openExternal) {
    void window.kda.openExternal(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export function ParentSetupWizard({
  open,
  message,
  hardware,
  catalog = [],
  onRefreshHardware,
  onSubmit,
}: Props) {
  const [step, setStep] = useState<StepId>("welcome");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [aiMode, setAiMode] = useState<"cloud" | "local" | "hybrid">("cloud");
  const [provider, setProvider] = useState<(typeof PROVIDERS)[number]["id"]>("openrouter");
  const [apiKey, setApiKey] = useState("");
  const [chatModel, setChatModel] = useState<string>(PROVIDERS[0].model);
  const [baseUrl, setBaseUrl] = useState<string>(PROVIDERS[0].baseUrl);
  const [budget, setBudget] = useState(2);
  const [ollamaUrl, setOllamaUrl] = useState("http://127.0.0.1:11434");
  const [localModel, setLocalModel] = useState("qwen3.5:9b-q4_K_M");
  const [dailyLimit, setDailyLimit] = useState(60);
  const [acceptLocalOffline, setAcceptLocalOffline] = useState(false);
  const [acceptNoVision, setAcceptNoVision] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [installBusy, setInstallBusy] = useState(false);
  const [installProgress, setInstallProgress] = useState<string | null>(null);
  const [installPercent, setInstallPercent] = useState<number | null>(null);
  const [pullAfterInstall, setPullAfterInstall] = useState(true);
  const [showTextOnly, setShowTextOnly] = useState(false);
  const canAutoInstall = Boolean(window.kda?.ollamaInstall);

  useEffect(() => {
    if (!open) return;
    setStep("welcome");
    setLocalError(null);
    setInstallBusy(false);
    setInstallProgress(null);
    setInstallPercent(null);
    setAcceptNoVision(false);
    setShowTextOnly(false);
    onRefreshHardware?.();
    // Reset only when the wizard opens; avoid re-running on parent re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open || !catalog.length) return;
    const preferred = catalog.find((item) => item.selected_default && item.vision !== false);
    const visionFallback = catalog.find((item) => item.vision);
    const next = preferred?.ollama || visionFallback?.ollama;
    if (next) setLocalModel(next);
  }, [open, catalog]);

  useEffect(() => {
    if (!open || !window.kda?.onOllamaProgress) return;
    return window.kda.onOllamaProgress((payload) => {
      if (payload.message) setInstallProgress(payload.message);
      if (typeof payload.percent === "number") setInstallPercent(payload.percent);
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    void window.kda?.resize?.(520, 720);
    return () => {
      void window.kda?.resize?.(320, 640);
    };
  }, [open]);

  if (!open) return null;

  const providerMeta = PROVIDERS.find((p) => p.id === provider) || PROVIDERS[0];
  const needsCloud = aiMode === "cloud" || aiMode === "hybrid";
  const needsLocal = aiMode === "local" || aiMode === "hybrid";
  const ollamaOk = Boolean(hardware?.ollama_ok);

  const steps: StepId[] = ["welcome", "pin", "mode"];
  if (needsCloud) steps.push("cloud");
  if (needsLocal) steps.push("local");
  steps.push("limits", "ready");

  const stepIndex = Math.max(0, steps.indexOf(step));

  function goNext() {
    setLocalError(null);
    if (step === "pin") {
      if (pin.length < 4) {
        setLocalError("Choose a PIN with at least 4 digits.");
        return;
      }
      if (pin !== confirmPin) {
        setLocalError("The PIN entries do not match.");
        return;
      }
    }
    if (step === "cloud") {
      if (!apiKey.trim()) {
        setLocalError("Paste your API key to use cloud AI, or go back and pick Local only.");
        return;
      }
    }
    if (step === "local") {
      if (installBusy) {
        setLocalError("Wait for Ollama install to finish.");
        return;
      }
      if (!ollamaOk && !acceptLocalOffline) {
        setLocalError(
          "Ollama is not detected yet. Tap Install Ollama, Check again, or confirm you’ll finish Ollama setup later."
        );
        return;
      }
      if (!looksLikeVisionModel(localModel) && !acceptNoVision) {
        setLocalError(
          "This app needs a vision model to see the screen (computer-use). Pick a “sees screen” model, or confirm chat-only."
        );
        return;
      }
    }
    const next = steps[stepIndex + 1];
    if (next) setStep(next);
  }

  function goBack() {
    setLocalError(null);
    const prev = steps[stepIndex - 1];
    if (prev) setStep(prev);
  }

  function pickProvider(id: (typeof PROVIDERS)[number]["id"]) {
    const meta = PROVIDERS.find((p) => p.id === id) || PROVIDERS[0];
    setProvider(id);
    setBaseUrl(meta.baseUrl);
    setChatModel(meta.model);
  }

  async function installOllama() {
    if (!window.kda?.ollamaInstall || installBusy) return;
    setLocalError(null);
    setInstallBusy(true);
    setInstallProgress("Starting Ollama install…");
    setInstallPercent(1);
    try {
      const result = await window.kda.ollamaInstall({
        pullModel: pullAfterInstall ? localModel : undefined,
      });
      if (!result.ok) {
        setLocalError(result.error || "Ollama install failed.");
        if (result.installed) setAcceptLocalOffline(true);
      } else {
        setInstallProgress(result.warning || "Ollama is ready.");
        setInstallPercent(100);
        setAcceptLocalOffline(false);
        if (result.warning) setLocalError(result.warning);
      }
      onRefreshHardware?.();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstallBusy(false);
    }
  }

  function submit() {
    if (pin.length < 4 || pin !== confirmPin) {
      setLocalError("Finish the PIN step before continuing.");
      setStep("pin");
      return;
    }
    if (needsCloud && !apiKey.trim()) {
      setLocalError("Cloud mode needs an API key.");
      setStep("cloud");
      return;
    }
    setLocalError(null);
    onSubmit({
      pin,
      ai_mode: aiMode,
      api_key: needsCloud ? apiKey.trim() : undefined,
      provider: needsCloud ? provider : undefined,
      base_url: needsCloud ? baseUrl : undefined,
      chat_model: needsCloud ? chatModel : undefined,
      daily_budget_usd: needsCloud ? budget : undefined,
      llm_model: needsLocal ? localModel : undefined,
      ollama_base_url: needsLocal ? ollamaUrl : undefined,
      daily_limit_minutes: dailyLimit,
    });
  }

  return (
    <div className="overlay" style={{ zIndex: 50 }}>
      <div className="modal parent-setup" role="dialog" aria-label="Parent setup">
        <div className="modal-header">
          <h2>Parent setup</h2>
          <span className="hint">
            Step {stepIndex + 1} / {steps.length}
          </span>
        </div>

        <div className="onboard-progress" aria-hidden>
          {steps.map((id, i) => (
            <span
              key={id}
              className={i === stepIndex ? "dot active" : i < stepIndex ? "dot done" : "dot"}
            />
          ))}
        </div>

        {step === "welcome" ? (
          <div className="setup-body">
            <p className="coach-line">Grown-ups first</p>
            <p className="hint">
              Before kids can play, set a parent PIN and choose how the AI should work on this PC —
              cloud (API key), local (Ollama), or both.
            </p>
            <p className="hint">
              This only happens once. You can change everything later under Grown-ups settings.
            </p>
          </div>
        ) : null}

        {step === "pin" ? (
          <div className="setup-body">
            <p className="coach-line">Choose a parent PIN</p>
            <p className="hint">Protects settings and computer-use approval. Min 4 digits.</p>
            <label>
              Parent PIN
              <input
                type="password"
                inputMode="numeric"
                value={pin}
                minLength={4}
                onChange={(e) => setPin(e.target.value)}
                autoFocus
              />
            </label>
            <label>
              Confirm PIN
              <input
                type="password"
                inputMode="numeric"
                value={confirmPin}
                minLength={4}
                onChange={(e) => setConfirmPin(e.target.value)}
              />
            </label>
          </div>
        ) : null}

        {step === "mode" ? (
          <div className="setup-body">
            <p className="coach-line">How should the AI run?</p>
            <button
              type="button"
              className={aiMode === "cloud" ? "setup-choice active" : "setup-choice"}
              onClick={() => setAiMode("cloud")}
            >
              <strong>Cloud</strong>
              <small>
                Every answer uses OpenRouter, OpenAI, or Gemini. Needs an API key and internet;
                costs count toward your daily cloud budget.
              </small>
            </button>
            <button
              type="button"
              className={aiMode === "local" ? "setup-choice active" : "setup-choice"}
              onClick={() => setAiMode("local")}
            >
              <strong>Local (Ollama)</strong>
              <small>
                Everything stays on this PC — free after install, private, and works offline.
                Needs disk space and a decent machine.
              </small>
            </button>
            <button
              type="button"
              className={aiMode === "hybrid" ? "setup-choice active" : "setup-choice"}
              onClick={() => setAiMode("hybrid")}
            >
              <strong>Hybrid</strong>
              <small>
                Local AI answers most questions for free and privately; trickier ones
                automatically use your cloud key. Needs both Ollama and an API key. Your daily
                cloud budget still caps spend.
              </small>
            </button>
          </div>
        ) : null}

        {step === "cloud" ? (
          <div className="setup-body">
            <p className="coach-line">Cloud API</p>
            <label>
              Provider
              <select
                value={provider}
                onChange={(e) => pickProvider(e.target.value as (typeof PROVIDERS)[number]["id"])}
              >
                {PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              API key
              <input
                type="password"
                value={apiKey}
                placeholder={providerMeta.keyHint}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label>
              Chat model
              <input value={chatModel} onChange={(e) => setChatModel(e.target.value)} />
            </label>
            <label>
              Daily cloud budget (USD soft cap)
              <input
                type="number"
                min={0}
                step={0.5}
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value) || 0)}
              />
            </label>
            <button type="button" className="chip" onClick={() => openLink(providerMeta.helpUrl)}>
              Get an API key
            </button>
            <p className="hint">Keys stay on this PC in the app data folder. Never share them with kids.</p>
          </div>
        ) : null}

        {step === "local" ? (
          <div className="setup-body">
            <p className="coach-line">Local AI (Ollama)</p>
            <p className="hint">
              Status:{" "}
              {ollamaOk ? (
                <strong className="ok-text">Ollama online</strong>
              ) : (
                <strong className="warn-text">Ollama not detected</strong>
              )}
              {hardware?.gpu_name ? ` · GPU: ${hardware.gpu_name}` : ""}
              {hardware?.vram_gb != null ? ` (${hardware.vram_gb} GB)` : ""}
            </p>
            {canAutoInstall ? (
              <>
                <p className="hint">
                  Don’t have Ollama yet? Install it here (official Windows installer from ollama.com).
                  Needs a few hundred MB for the app, plus several GB if you download a model.
                </p>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={pullAfterInstall}
                    onChange={(e) => setPullAfterInstall(e.target.checked)}
                    disabled={installBusy}
                  />
                  Also download model <code>{localModel}</code> after install
                </label>
                <div className="preset-row">
                  <button
                    type="button"
                    className="primary-btn"
                    onClick={() => void installOllama()}
                    disabled={installBusy || ollamaOk}
                  >
                    {installBusy ? "Installing…" : ollamaOk ? "Ollama installed" : "Install Ollama"}
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => onRefreshHardware?.()}
                    disabled={installBusy}
                  >
                    Check again
                  </button>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => openLink(OLLAMA_URL)}
                    disabled={installBusy}
                  >
                    Manual download
                  </button>
                </div>
                {installProgress ? (
                  <div className="setup-progress">
                    <p className="hint">{installProgress}</p>
                    {installPercent != null ? (
                      <div className="setup-progress-bar" aria-hidden>
                        <span style={{ width: `${Math.max(2, Math.min(100, installPercent))}%` }} />
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <div className="preset-row">
                  <button type="button" className="chip" onClick={() => openLink(OLLAMA_URL)}>
                    Download Ollama
                  </button>
                  <button type="button" className="chip" onClick={() => onRefreshHardware?.()}>
                    Check again
                  </button>
                </div>
                <p className="hint">
                  After installing: open Ollama, then in a terminal run{" "}
                  <code>ollama pull {localModel}</code>
                </p>
              </>
            )}
            <label>
              Ollama URL
              <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
            </label>
            <p className="hint">
              Pick a model that <strong>sees the screen</strong> (vision encoder). Text-only models
              cannot do computer-use screenshots. We pre-select the best fit for this PC.
            </p>
            <label>
              Local model
              <input
                value={localModel}
                onChange={(e) => {
                  setLocalModel(e.target.value);
                  setAcceptNoVision(false);
                }}
              />
            </label>
            {!looksLikeVisionModel(localModel) ? (
              <p className="hint warn-text">
                Current choice looks text-only — screen vision will not work until you pick a VL /
                vision model.
              </p>
            ) : (
              <p className="hint ok-text">Vision model selected — can understand screenshots.</p>
            )}
            {catalog.length > 0 ? (
              <div className="preset-row">
                {catalog
                  .filter((item) => item.vision !== false)
                  .map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={
                        localModel === item.ollama
                          ? "chip chip-selected"
                          : item.selected_default
                            ? "chip chip-recommended"
                            : "chip"
                      }
                      title={item.notes || item.fit}
                      onClick={() => {
                        setLocalModel(item.ollama);
                        setAcceptNoVision(false);
                      }}
                    >
                      {item.selected_default ? "★ " : ""}
                      {item.label}
                      {item.fit ? ` · ${item.fit}` : ""}
                    </button>
                  ))}
              </div>
            ) : null}
            <button
              type="button"
              className="chip"
              onClick={() => setShowTextOnly((v) => !v)}
            >
              {showTextOnly ? "Hide text-only models" : "Show text-only models (no screen vision)"}
            </button>
            {showTextOnly && catalog.some((item) => item.vision === false) ? (
              <div className="preset-row">
                {catalog
                  .filter((item) => item.vision === false)
                  .map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="chip"
                      title={item.notes || item.fit}
                      onClick={() => setLocalModel(item.ollama)}
                    >
                      {item.label} · text only
                    </button>
                  ))}
              </div>
            ) : null}
            {hardware?.ollama_models && hardware.ollama_models.length > 0 ? (
              <div className="preset-row">
                {hardware.ollama_models.map((m) => (
                  <button
                    key={m}
                    type="button"
                    className="chip"
                    onClick={() => {
                      setLocalModel(m);
                      setAcceptNoVision(false);
                    }}
                  >
                    installed: {m}
                    {looksLikeVisionModel(m) ? " · vision" : " · text?"}
                  </button>
                ))}
              </div>
            ) : null}
            {!ollamaOk ? (
              <label className="check">
                <input
                  type="checkbox"
                  checked={acceptLocalOffline}
                  onChange={(e) => setAcceptLocalOffline(e.target.checked)}
                />
                I’ll finish installing Ollama after setup
              </label>
            ) : null}
            {!looksLikeVisionModel(localModel) ? (
              <label className="check">
                <input
                  type="checkbox"
                  checked={acceptNoVision}
                  onChange={(e) => setAcceptNoVision(e.target.checked)}
                />
                Use text-only anyway (chat/tools only — no screenshot understanding)
              </label>
            ) : null}
          </div>
        ) : null}

        {step === "limits" ? (
          <div className="setup-body">
            <p className="coach-line">Play time & privacy</p>
            <label>
              Default daily play limit (minutes)
              <input
                type="number"
                min={15}
                max={240}
                value={dailyLimit}
                onChange={(e) => setDailyLimit(Number(e.target.value) || 60)}
              />
            </label>
            <p className="hint">
              Chat, transcripts, screenshots, and kid recognition data stay on this PC. Cloud mode
              also sends chat to your chosen provider.
            </p>
            <p className="hint">
              Computer-use (screen click/type) stays <strong>off</strong>. You can enable it later
              with PIN gates and a visible Stop control.
            </p>
          </div>
        ) : null}

        {step === "ready" ? (
          <div className="setup-body">
            <p className="coach-line">Ready to save</p>
            <ul className="setup-summary">
              <li>PIN set</li>
              <li>
                Mode: <strong>{aiMode}</strong>
              </li>
              {needsCloud ? (
                <li>
                  Cloud: {providerMeta.label} · model {chatModel}
                </li>
              ) : null}
              {needsLocal ? (
                <li>
                  Ollama: {ollamaOk ? "online" : "not detected yet"} · {localModel}
                </li>
              ) : null}
              <li>Daily limit: {dailyLimit} min</li>
            </ul>
            <p className="hint">After this, kids can onboarding and play. Grown-ups can change settings anytime with the PIN.</p>
          </div>
        ) : null}

        {localError || message ? <p className="error">{localError || message}</p> : null}

        <div className="onboard-nav">
          {stepIndex > 0 ? (
            <button type="button" className="guide-secondary" onClick={goBack}>
              Back
            </button>
          ) : (
            <span />
          )}
          {step === "ready" ? (
            <button type="button" className="primary-btn" onClick={submit}>
              Finish setup
            </button>
          ) : (
            <button type="button" className="primary-btn" onClick={goNext}>
              {step === "welcome" ? "Start" : "Next"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
