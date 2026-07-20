import { useState } from "react";

type Props = {
  open: boolean;
  message?: string | null;
  onSubmit: (payload: {
    pin: string;
    ai_mode: "cloud" | "local" | "hybrid";
    api_key?: string;
    daily_limit_minutes: number;
  }) => void;
};

export function ParentSetupWizard({ open, message, onSubmit }: Props) {
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [aiMode, setAiMode] = useState<"cloud" | "local" | "hybrid">("cloud");
  const [apiKey, setApiKey] = useState("");
  const [dailyLimit, setDailyLimit] = useState(60);
  const [localError, setLocalError] = useState<string | null>(null);

  if (!open) return null;

  function submit() {
    if (pin.length < 4) {
      setLocalError("Choose a PIN with at least 4 digits.");
      return;
    }
    if (pin !== confirmPin) {
      setLocalError("The PIN entries do not match.");
      return;
    }
    setLocalError(null);
    onSubmit({
      pin,
      ai_mode: aiMode,
      api_key: apiKey.trim() || undefined,
      daily_limit_minutes: dailyLimit,
    });
  }

  return (
    <div className="overlay">
      <div className="modal parent-setup" role="dialog" aria-label="Parent setup">
        <div className="modal-header">
          <h2>Parent setup</h2>
        </div>
        <p className="hint">
          First choose a parent PIN. Installed builds do not use the dev PIN.
        </p>

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

        <label>
          AI mode
          <select value={aiMode} onChange={(e) => setAiMode(e.target.value as typeof aiMode)}>
            <option value="cloud">Cloud</option>
            <option value="local">Local Ollama</option>
            <option value="hybrid">Hybrid</option>
          </select>
        </label>

        <label>
          Cloud API key
          <input
            type="password"
            value={apiKey}
            placeholder="Optional"
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>

        <label>
          Daily play limit
          <input
            type="number"
            min={15}
            max={240}
            value={dailyLimit}
            onChange={(e) => setDailyLimit(Number(e.target.value) || 60)}
          />
        </label>

        <p className="hint">
          Chat, transcripts, screenshots, and kid recognition data are stored locally under the app data folder. Cloud mode sends chat to the configured provider.
        </p>
        <p className="hint">
          Computer-use starts off. A parent can enable it later with PIN gates and a visible Stop control.
        </p>

        {localError || message ? <p className="error">{localError || message}</p> : null}

        <button type="button" className="primary-btn" onClick={submit}>
          Save parent setup
        </button>
      </div>
    </div>
  );
}
