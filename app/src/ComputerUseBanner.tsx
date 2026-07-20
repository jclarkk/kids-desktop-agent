import { useEffect, useState } from "react";

export type ComputerUseStatus = {
  mode?: string;
  enabled?: boolean;
  session_active?: boolean;
  session_remaining_sec?: number | null;
  driving?: boolean;
  pending?: {
    id: string;
    name: string;
    arguments?: Record<string, unknown>;
  } | null;
};

type Props = {
  status?: ComputerUseStatus | null;
  onStop: () => void;
  onApprove: (pin: string) => void;
  onDeny: () => void;
  onStartSession: (pin: string) => void;
  message?: string | null;
};

function actionLabel(name?: string) {
  if (name === "computer_screenshot") return "Take a screenshot";
  if (name === "computer_click") return "Click the screen";
  if (name === "computer_type") return "Type on the keyboard";
  return name || "Computer action";
}

export function ComputerUseBanner({
  status,
  onStop,
  onApprove,
  onDeny,
  onStartSession,
  message,
}: Props) {
  const [pin, setPin] = useState("");
  const pending = status?.pending;
  const driving = Boolean(status?.driving);
  const sessionMode = status?.mode === "session";
  const showSessionStart =
    sessionMode && status?.enabled && !status.session_active && !pending;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && driving) {
        e.preventDefault();
        onStop();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [driving, onStop]);

  if (!status?.enabled && !driving) return null;
  const cu = status || {};

  return (
    <div className={`cu-banner ${driving ? "cu-driving" : ""}`} role="status">
      <div className="cu-banner-main">
        <strong>{driving ? "Robot driving" : "Computer help"}</strong>
        <span>
          {pending
            ? `Parent PIN needed: ${actionLabel(pending.name)}`
            : cu.session_active
              ? `Session · ${cu.session_remaining_sec ?? "?"}s left · Esc = stop`
              : cu.mode === "ask"
                ? "Ask each time (PIN)"
                : cu.mode === "session"
                  ? "Session mode — start with PIN"
                  : "Off"}
        </span>
        {message ? <em className="cu-msg">{message}</em> : null}
      </div>

      <div className="cu-banner-actions">
        {driving ? (
          <button type="button" className="cu-stop" onClick={onStop}>
            Stop
          </button>
        ) : null}

        {pending ? (
          <>
            <input
              type="password"
              inputMode="numeric"
              autoComplete="off"
              placeholder="PIN"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              maxLength={12}
            />
            <button
              type="button"
              onClick={() => {
                onApprove(pin);
                setPin("");
              }}
            >
              Approve
            </button>
            <button type="button" className="ghost" onClick={onDeny}>
              No
            </button>
          </>
        ) : null}

        {showSessionStart ? (
          <>
            <input
              type="password"
              inputMode="numeric"
              autoComplete="off"
              placeholder="PIN to start"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              maxLength={12}
            />
            <button
              type="button"
              onClick={() => {
                onStartSession(pin);
                setPin("");
              }}
            >
              Start session
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}
