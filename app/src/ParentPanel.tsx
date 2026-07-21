import { useEffect, useState } from "react";

export type AllowApp = {
  id: string;
  label: string;
  windows?: { command?: string; args?: string[] };
  macos?: { command?: string; args?: string[] };
};

export type AllowSite = { id: string; label: string; url: string };

export type CatalogItem = {
  id: string;
  label: string;
  ollama: string;
  fit: string;
  notes?: string;
  vision?: boolean;
  selected_default?: boolean;
};

export type ParentSettings = {
  parent_pin?: string;
  ai_mode?: string;
  cloud?: {
    provider?: string;
    api_key?: string;
    api_key_set?: boolean;
    base_url?: string;
    chat_model?: string;
    daily_budget_usd?: number;
    presets?: Record<string, string>;
  };
  local?: {
    llm_model?: string;
    ollama_base_url?: string;
    gpu_layers?: string | number;
    allow_offload?: boolean;
    stt_model?: string;
  };
  kids?: Array<{
    id: string;
    name: string;
    age: number;
    preferred_avatar?: string;
    preferred_gender?: "boy" | "girl" | "neutral";
    daily_limit_minutes?: number;
    english_level?: "beginner" | "elementary" | "intermediate";
  }>;
  allowlist?: {
    skills_enabled?: string[];
    apps?: AllowApp[];
    websites?: AllowSite[];
  };
  computer_use?: { mode?: string };
  safety?: {
    log_transcripts?: boolean;
    content_strictness?: string;
  };
  identity?: {
    require_who_is_playing?: boolean;
    voice_name_match?: boolean;
    face_match?: boolean;
    allow_tap_select?: boolean;
    face_match_threshold?: number;
  };
};

const SKILL_OPTIONS = [
  "open_app",
  "open_website",
  "set_volume",
  "start_timer",
  "list_windows",
];

const TABS = [
  { id: "ai", label: "AI" },
  { id: "kids", label: "Kids" },
  { id: "allow", label: "Apps & Sites" },
  { id: "computer", label: "Computer use" },
  { id: "safety", label: "Safety & PIN" },
] as const;

type TabId = (typeof TABS)[number]["id"];

type Props = {
  open: boolean;
  onClose: () => void;
  onUnlock: (pin: string) => void;
  unlocked: boolean;
  error: string | null;
  settings: ParentSettings | null;
  saveMessage: string | null;
  onSave: (patch: Record<string, unknown>) => void;
  catalog?: CatalogItem[];
  hardware?: {
    vram_gb?: number | null;
    gpu_name?: string | null;
    ollama_ok?: boolean;
    ollama_models?: string[];
  } | null;
  budget?: { spent_usd?: number; limit_usd?: number; remaining_usd?: number } | null;
  onRefreshHardware?: () => void;
  onAddKid?: () => void;
  onPrivacyClear?: (target: "transcripts" | "screenshots" | "kid_data") => void;
};

export function ParentPanel({
  open,
  onClose,
  onUnlock,
  unlocked,
  error,
  settings,
  saveMessage,
  onSave,
  catalog = [],
  hardware,
  budget,
  onRefreshHardware,
  onAddKid,
  onPrivacyClear,
}: Props) {
  const [tab, setTab] = useState<TabId>("ai");
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState("openrouter");
  const [baseUrl, setBaseUrl] = useState("https://openrouter.ai/api/v1");
  const [model, setModel] = useState("google/gemini-2.5-flash");
  const [budgetLimit, setBudgetLimit] = useState(2);
  const [aiMode, setAiMode] = useState("cloud");
  const [skills, setSkills] = useState<string[]>(SKILL_OPTIONS);
  const [apps, setApps] = useState<AllowApp[]>([]);
  const [sites, setSites] = useState<AllowSite[]>([]);
  const [newPin, setNewPin] = useState("");
  const [computerUse, setComputerUse] = useState("off");
  const [logTranscripts, setLogTranscripts] = useState(true);
  const [contentStrictness, setContentStrictness] = useState("strict");
  const [computerUseWarning, setComputerUseWarning] = useState<"ask" | "session" | null>(null);
  const [localModel, setLocalModel] = useState("qwen3.5:9b-q4_K_M");
  const [ollamaUrl, setOllamaUrl] = useState("http://127.0.0.1:11434");
  const [gpuLayers, setGpuLayers] = useState("auto");
  const [allowOffload, setAllowOffload] = useState(true);
  const [requireGate, setRequireGate] = useState(true);
  const [voiceMatch, setVoiceMatch] = useState(true);
  const [faceMatch, setFaceMatch] = useState(true);
  const [kids, setKids] = useState<
    Array<{
      id: string;
      name: string;
      age: number;
      preferred_avatar?: string;
      preferred_gender?: "boy" | "girl" | "neutral";
      daily_limit_minutes?: number;
      english_level?: "beginner" | "elementary" | "intermediate";
    }>
  >([]);

  useEffect(() => {
    if (!settings) return;
    setProvider(settings.cloud?.provider || "openrouter");
    setBaseUrl(settings.cloud?.base_url || "https://openrouter.ai/api/v1");
    setModel(settings.cloud?.chat_model || "google/gemini-2.5-flash");
    setBudgetLimit(settings.cloud?.daily_budget_usd ?? 2);
    setAiMode(settings.ai_mode || "cloud");
    setSkills(settings.allowlist?.skills_enabled || SKILL_OPTIONS);
    setApps(settings.allowlist?.apps || []);
    setSites(settings.allowlist?.websites || []);
    setComputerUse(settings.computer_use?.mode || "off");
    setLogTranscripts(settings.safety?.log_transcripts ?? true);
    setContentStrictness(settings.safety?.content_strictness || "strict");
    setLocalModel(settings.local?.llm_model || "qwen3.5:9b-q4_K_M");
    setOllamaUrl(settings.local?.ollama_base_url || "http://127.0.0.1:11434");
    setGpuLayers(String(settings.local?.gpu_layers ?? "auto"));
    setAllowOffload(settings.local?.allow_offload ?? true);
    setRequireGate(settings.identity?.require_who_is_playing ?? true);
    setVoiceMatch(settings.identity?.voice_name_match ?? true);
    setFaceMatch(settings.identity?.face_match ?? true);
    setKids(settings.kids || []);
    setApiKey("");
  }, [settings]);

  useEffect(() => {
    if (open) setTab("ai");
  }, [open]);

  if (!open) return null;

  const presets = settings?.cloud?.presets || {};

  return (
    <div className="overlay" style={{ zIndex: 40 }}>
      <div className="modal parent-panel" role="dialog" aria-label="Parent settings">
        <div className="modal-header">
          <h2>Parent settings</h2>
          <button type="button" className="close-x" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        {!unlocked ? (
          <form
            className="pin-form"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              onUnlock(String(fd.get("pin") || ""));
            }}
          >
            <div className="pin-emoji">🔒</div>
            <p className="coach-sub">Grown-ups only — enter your PIN.</p>
            <input
              name="pin"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={12}
              autoFocus
              aria-label="PIN"
            />
            <button type="submit" className="primary-btn">
              Unlock
            </button>
            {error ? <p className="error">{error}</p> : null}
            <p className="hint">
              Dev default PIN is 1234 — change it in Safety &amp; PIN after unlock (stored
              hashed).
            </p>
          </form>
        ) : (
          <form
            className="parent-body"
            onSubmit={(e) => {
              e.preventDefault();
              const patch: Record<string, unknown> = {
                ai_mode: aiMode,
                cloud: {
                  provider,
                  base_url: baseUrl,
                  chat_model: model,
                  daily_budget_usd: budgetLimit,
                  ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
                },
                local: {
                  llm_model: localModel,
                  ollama_base_url: ollamaUrl,
                  gpu_layers: gpuLayers === "auto" ? "auto" : Number(gpuLayers),
                  allow_offload: allowOffload,
                },
                kids,
                identity: {
                  require_who_is_playing: requireGate,
                  voice_name_match: voiceMatch,
                  face_match: faceMatch,
                  allow_tap_select: true,
                },
                allowlist: {
                  skills_enabled: skills,
                  apps,
                  websites: sites,
                },
                computer_use: { mode: computerUse },
                safety: { log_transcripts: logTranscripts, content_strictness: contentStrictness },
              };
              if (newPin.trim().length >= 4) patch.parent_pin = newPin.trim();
              onSave(patch);
            }}
          >
            <div className="tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  className={tab === t.id ? "tab-btn active" : "tab-btn"}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === "ai" ? (
              <>
                <div className="section">
                  <h3>Mode</h3>
                  <label>
                    AI mode
                    <select value={aiMode} onChange={(e) => setAiMode(e.target.value)}>
                      <option value="cloud">Cloud (API — every answer online)</option>
                      <option value="hybrid">Hybrid (local first, cloud for hard questions)</option>
                      <option value="local">Local (Ollama — on this PC only)</option>
                    </select>
                  </label>
                  <p className="hint">
                    {aiMode === "hybrid"
                      ? "Hybrid keeps most chat on Ollama. Harder questions (long text, math, deep explain) use your cloud key when budget allows. If Ollama fails, one cloud retry is tried."
                      : aiMode === "local"
                        ? "All answers stay on this computer. No cloud API spend."
                        : "All answers use your cloud provider. Soft daily budget still applies."}
                  </p>
                </div>

                <div className="section">
                  <h3>Cloud</h3>
                  <label>
                    Provider
                    <select
                      value={provider}
                      onChange={(e) => {
                        const next = e.target.value;
                        setProvider(next);
                        if (next === "openrouter") setBaseUrl("https://openrouter.ai/api/v1");
                        if (next === "openai") setBaseUrl("https://api.openai.com/v1");
                        if (next === "gemini")
                          setBaseUrl("https://generativelanguage.googleapis.com/v1beta/openai/");
                      }}
                    >
                      <option value="openrouter">OpenRouter</option>
                      <option value="openai">OpenAI</option>
                      <option value="gemini">Gemini (OpenAI-compatible)</option>
                    </select>
                  </label>
                  <label>
                    API key {settings?.cloud?.api_key_set ? "(saved — leave blank to keep)" : ""}
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder={settings?.cloud?.api_key_set ? "•••• saved" : "sk-… or or-…"}
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    Base URL
                    <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
                  </label>
                  <label>
                    Chat model
                    <input value={model} onChange={(e) => setModel(e.target.value)} />
                  </label>
                  {Object.keys(presets).length > 0 ? (
                    <div className="preset-row">
                      {Object.entries(presets).map(([name, slug]) => (
                        <button
                          key={name}
                          type="button"
                          className="chip"
                          onClick={() => setModel(slug)}
                        >
                          {name}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <label>
                    Daily budget (USD soft cap)
                    <input
                      type="number"
                      min={0}
                      step={0.5}
                      value={budgetLimit}
                      onChange={(e) => setBudgetLimit(Number(e.target.value))}
                    />
                  </label>
                  {budget ? (
                    <p className="hint">
                      Today: ${budget.spent_usd?.toFixed(3) ?? "0"} / $
                      {budget.limit_usd ?? budgetLimit} (${budget.remaining_usd?.toFixed(3) ?? "?"}{" "}
                      left)
                    </p>
                  ) : null}
                </div>

                  <div className="section">
                  <h3>Local (Ollama)</h3>
                  <p className="hint">
                    GPU: {hardware?.gpu_name || "unknown"}{" "}
                    {hardware?.vram_gb != null ? `(${hardware.vram_gb} GB)` : "(CPU / no nvidia-smi)"}{" "}
                    · Ollama {hardware?.ollama_ok ? "online" : "offline"}
                  </p>
                  <p className="hint">
                    Prefer a <strong>vision</strong> model (Qwen3.5 / Gemma 4, quantized) so the
                    avatar can understand screenshots for computer-use. Text-only models cannot.
                  </p>
                  <div className="preset-row">
                    <button type="button" className="chip" onClick={() => onRefreshHardware?.()}>
                      Refresh hardware
                    </button>
                  </div>
                  <label>
                    Ollama URL
                    <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
                  </label>
                  <label>
                    Local model
                    <input value={localModel} onChange={(e) => setLocalModel(e.target.value)} />
                  </label>
                  {!(
                    /(?:^|[:/\-_])(?:vl|vision|llava|moondream|minicpm-v)(?:$|[:/\-_\d])/i.test(
                      localModel
                    ) ||
                    localModel.toLowerCase().startsWith("qwen3.5") ||
                    localModel.toLowerCase().startsWith("gemma4") ||
                    localModel.toLowerCase().includes("gemma3")
                  ) ? (
                    <p className="hint" style={{ color: "#b45309" }}>
                      This model name does not look vision-capable. Computer-use screenshots may
                      fail — switch to Qwen3.5 or Gemma 4 below.
                    </p>
                  ) : null}
                  <div className="preset-row">
                    {catalog.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className="chip"
                        title={`${item.notes || ""} [${item.fit}]`}
                        onClick={() => setLocalModel(item.ollama)}
                      >
                        {item.selected_default ? "★ " : ""}
                        {item.label}
                        {item.vision === false ? " · text" : " · vision"} · {item.fit}
                      </button>
                    ))}
                  </div>
                  {hardware?.ollama_models && hardware.ollama_models.length > 0 ? (
                    <div className="preset-row">
                      {hardware.ollama_models.map((m) => (
                        <button
                          key={m}
                          type="button"
                          className="chip"
                          onClick={() => setLocalModel(m)}
                        >
                          installed: {m}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <label>
                    GPU layers (auto or number for offload)
                    <input value={gpuLayers} onChange={(e) => setGpuLayers(e.target.value)} />
                  </label>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={allowOffload}
                      onChange={(e) => setAllowOffload(e.target.checked)}
                    />
                    Allow larger models via CPU offload (slower)
                  </label>
                </div>
              </>
            ) : null}

            {tab === "kids" ? (
              <>
                <div className="section">
                  <h3>Kid profiles</h3>
                  {kids.map((kid, idx) => (
                    <div key={`${kid.id}-${idx}`} className="allow-row kids-row">
                      <input
                        value={kid.name}
                        placeholder="name"
                        onChange={(e) => {
                          const next = [...kids];
                          next[idx] = { ...kid, name: e.target.value };
                          setKids(next);
                        }}
                      />
                      <input
                        type="number"
                        min={2}
                        max={18}
                        value={kid.age}
                        placeholder="age"
                        onChange={(e) => {
                          const next = [...kids];
                          next[idx] = { ...kid, age: Number(e.target.value) };
                          setKids(next);
                        }}
                      />
                      <select
                        value={kid.english_level || "beginner"}
                        title="English level"
                        onChange={(e) => {
                          const next = [...kids];
                          next[idx] = {
                            ...kid,
                            english_level: e.target.value as
                              | "beginner"
                              | "elementary"
                              | "intermediate",
                          };
                          setKids(next);
                        }}
                      >
                        <option value="beginner">English: new</option>
                        <option value="elementary">English: some</option>
                        <option value="intermediate">English: more</option>
                      </select>
                      <input
                        type="number"
                        value={kid.daily_limit_minutes ?? 60}
                        placeholder="mins/day"
                        onChange={(e) => {
                          const next = [...kids];
                          next[idx] = { ...kid, daily_limit_minutes: Number(e.target.value) };
                          setKids(next);
                        }}
                      />
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => setKids(kids.filter((_, i) => i !== idx))}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <div className="preset-row">
                    <button type="button" className="chip" onClick={() => onAddKid?.()}>
                      + Add a kid (guided onboarding)
                    </button>
                  </div>
                </div>

                <div className="section">
                  <h3>Who is playing</h3>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={requireGate}
                      onChange={(e) => setRequireGate(e.target.checked)}
                    />
                    Ask who is playing when no kid is selected
                  </label>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={voiceMatch}
                      onChange={(e) => setVoiceMatch(e.target.checked)}
                    />
                    Allow “say my name” voice match (local)
                  </label>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={faceMatch}
                      onChange={(e) => setFaceMatch(e.target.checked)}
                    />
                    Allow camera face match (local soft match)
                  </label>
                  <p className="hint">
                    Face/voice data stays on this PC under data/kids/. Not security-grade ID.
                  </p>
                </div>
              </>
            ) : null}

            {tab === "allow" ? (
              <>
                <div className="section">
                  <h3>Enabled skills</h3>
                  {SKILL_OPTIONS.map((skill) => (
                    <label key={skill} className="check">
                      <input
                        type="checkbox"
                        checked={skills.includes(skill)}
                        onChange={(e) => {
                          setSkills((prev) =>
                            e.target.checked ? [...prev, skill] : prev.filter((s) => s !== skill)
                          );
                        }}
                      />
                      {skill}
                    </label>
                  ))}
                </div>

                <div className="section">
                  <h3>Allowlisted apps</h3>
                  {apps.map((app, idx) => (
                    <div key={`${app.id}-${idx}`} className="allow-row">
                      <input
                        value={app.id}
                        placeholder="id"
                        onChange={(e) => {
                          const next = [...apps];
                          next[idx] = { ...app, id: e.target.value };
                          setApps(next);
                        }}
                      />
                      <input
                        value={app.label}
                        placeholder="label"
                        onChange={(e) => {
                          const next = [...apps];
                          next[idx] = { ...app, label: e.target.value };
                          setApps(next);
                        }}
                      />
                      <input
                        value={app.windows?.command || ""}
                        placeholder="windows command"
                        onChange={(e) => {
                          const next = [...apps];
                          next[idx] = {
                            ...app,
                            windows: { ...(app.windows || {}), command: e.target.value },
                          };
                          setApps(next);
                        }}
                      />
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => setApps(apps.filter((_, i) => i !== idx))}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <div className="preset-row">
                    <button
                      type="button"
                      className="chip"
                      onClick={() =>
                        setApps([
                          ...apps,
                          {
                            id: "app",
                            label: "App",
                            windows: { command: "" },
                            macos: { command: "open" },
                          },
                        ])
                      }
                    >
                      + Add app
                    </button>
                  </div>
                </div>

                <div className="section">
                  <h3>Allowlisted websites</h3>
                  {sites.map((site, idx) => (
                    <div key={`${site.id}-${idx}`} className="allow-row">
                      <input
                        value={site.id}
                        placeholder="id"
                        onChange={(e) => {
                          const next = [...sites];
                          next[idx] = { ...site, id: e.target.value };
                          setSites(next);
                        }}
                      />
                      <input
                        value={site.label}
                        placeholder="label"
                        onChange={(e) => {
                          const next = [...sites];
                          next[idx] = { ...site, label: e.target.value };
                          setSites(next);
                        }}
                      />
                      <input
                        value={site.url}
                        placeholder="https://"
                        onChange={(e) => {
                          const next = [...sites];
                          next[idx] = { ...site, url: e.target.value };
                          setSites(next);
                        }}
                      />
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => setSites(sites.filter((_, i) => i !== idx))}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <div className="preset-row">
                    <button
                      type="button"
                      className="chip"
                      onClick={() =>
                        setSites([...sites, { id: "site", label: "Site", url: "https://" }])
                      }
                    >
                      + Add website
                    </button>
                  </div>
                </div>
              </>
            ) : null}

            {tab === "computer" ? (
              <div className="section">
                <h3>Computer use</h3>
                <label>
                  Mode
                  <select
                    value={computerUse}
                    onChange={(e) => {
                      const next = e.target.value;
                      if (next !== "off" && computerUse === "off") {
                        setComputerUseWarning(next as "ask" | "session");
                        return;
                      }
                      setComputerUse(next);
                    }}
                  >
                    <option value="off">Off</option>
                    <option value="ask">Ask each time (PIN)</option>
                    <option value="session">Session approved (PIN once)</option>
                  </select>
                </label>
                <p className="hint">
                  When on, the avatar may screenshot (vision), click, and type after a parent PIN.
                  A red “Robot driving” banner shows; Esc or Stop ends control. Prefer a
                  vision-capable cloud model (e.g. Gemini Flash) or a local vision model in
                  Ollama.
                </p>
                  {computerUseWarning ? (
                    <div className="warning-box">
                      <strong>Before enabling computer-use</strong>
                      <p>
                        Screenshots may be sent to the configured AI model for vision. The avatar
                        can click and type only after a parent PIN, and the Stop/Esc control remains
                        available without a PIN.
                      </p>
                      <div className="preset-row">
                        <button
                          type="button"
                          className="chip active"
                          onClick={() => {
                            setComputerUse(computerUseWarning);
                            setComputerUseWarning(null);
                          }}
                        >
                          I understand
                        </button>
                        <button
                          type="button"
                          className="chip"
                          onClick={() => setComputerUseWarning(null)}
                        >
                          Keep off
                        </button>
                      </div>
                    </div>
                  ) : null}
              </div>
            ) : null}

            {tab === "safety" ? (
              <>
                <div className="section">
                  <h3>Safety</h3>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={logTranscripts}
                      onChange={(e) => setLogTranscripts(e.target.checked)}
                    />
                    Log transcripts locally
                  </label>
                  <label>
                    Content filter
                    <select
                      value={contentStrictness}
                      onChange={(e) => setContentStrictness(e.target.value)}
                    >
                      <option value="strict">Strict (recommended)</option>
                      <option value="standard">Standard</option>
                    </select>
                  </label>
                  <p className="hint">
                    Filtering runs locally for every message. Cloud moderation is also used when
                    supported by the configured cloud provider.
                  </p>
                </div>

                <div className="section">
                  <h3>Local privacy data</h3>
                  <p className="hint">
                    Clear local records stored on this PC. Kid profile names stay unless removed in
                    the Kids tab.
                  </p>
                  <div className="preset-row">
                    <button
                      type="button"
                      className="chip"
                      onClick={() => onPrivacyClear?.("transcripts")}
                    >
                      Clear transcripts
                    </button>
                    <button
                      type="button"
                      className="chip"
                      onClick={() => onPrivacyClear?.("screenshots")}
                    >
                      Clear screenshots
                    </button>
                    <button
                      type="button"
                      className="chip"
                      onClick={() => onPrivacyClear?.("kid_data")}
                    >
                      Clear face/voice data
                    </button>
                  </div>
                </div>

                <div className="section">
                  <h3>Parent PIN</h3>
                  <label>
                    New PIN (min 4 digits — stored as hash)
                    <input
                      type="password"
                      value={newPin}
                      onChange={(e) => setNewPin(e.target.value)}
                      placeholder="Leave blank to keep"
                      autoComplete="off"
                    />
                  </label>
                  <p className="hint">
                    The installer will ask for a PIN during setup. In dev mode the default is
                    1234 — please change it.
                  </p>
                </div>
              </>
            ) : null}

            <div className="parent-footer">
              <button type="submit" className="primary-btn">
                Save
              </button>
              {saveMessage ? <p className="hint">{saveMessage}</p> : null}
              {error ? <p className="error">{error}</p> : null}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
