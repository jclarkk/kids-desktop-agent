import { useEffect, useState } from "react";
import { CHARACTER_EMOJI } from "./AvatarFace";
import { DEFAULT_PTT_KEY, keyLabel } from "./usePushToTalk";

export type AvatarCharacter = {
  id: string;
  name: string;
  description?: string;
  genders: Array<"boy" | "girl" | "neutral">;
  default_gender?: string;
  voices?: Record<string, string>;
};

export type AvatarPack = {
  id: string;
  name: string;
  characters: AvatarCharacter[];
};

type Props = {
  open: boolean;
  onClose: () => void;
  packs: AvatarPack[];
  packId: string;
  characterId: string;
  gender: "boy" | "girl" | "neutral";
  onAvatarChange: (next: {
    pack_id: string;
    character_id: string;
    gender: "boy" | "girl" | "neutral";
  }) => void;
  games: Array<{ id: string; label: string }>;
  activeGame: { kind: string; prompt: string } | null;
  onStartGame: (kind: string) => void;
  onCancelGame: () => void;
  showKidSwitch: boolean;
  onSwitchKid: () => void;
  onOpenParent: () => void;
  pttKey: string;
  onSetPttKey: (code: string) => void;
  usage?: {
    used_minutes?: number;
    limit_minutes?: number;
    over_limit?: boolean;
  } | null;
};

const GAME_EMOJI: Record<string, string> = {
  word_of_the_day: "📖",
  repeat_after_me: "🔁",
  phonics: "🎵",
  spell: "🔤",
  i_spy: "👀",
};

const GENDER_LABEL: Record<string, string> = {
  boy: "Boy voice",
  girl: "Girl voice",
  neutral: "Soft voice",
};

export function KidMenu({
  open,
  onClose,
  packs,
  packId,
  characterId,
  gender,
  onAvatarChange,
  games,
  activeGame,
  onStartGame,
  onCancelGame,
  showKidSwitch,
  onSwitchKid,
  onOpenParent,
  pttKey,
  onSetPttKey,
  usage,
}: Props) {
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    if (!capturing) return;
    function onKey(e: KeyboardEvent) {
      e.preventDefault();
      e.stopPropagation();
      if (e.code === "Escape") {
        setCapturing(false);
        return;
      }
      onSetPttKey(e.code);
      setCapturing(false);
    }
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [capturing, onSetPttKey]);

  useEffect(() => {
    if (!open) setCapturing(false);
  }, [open]);

  if (!open) return null;

  const pack = packs.find((p) => p.id === packId) || packs[0];
  const characters = pack?.characters || [];

  return (
    <div className="overlay">
      <div className="modal" role="dialog" aria-label="Menu">
        <div className="modal-header">
          <h2>Menu</h2>
          <button type="button" className="close-x" aria-label="Close menu" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="section">
          <h3>My friend</h3>
          <div className="character-row">
            {characters.map((ch) => (
              <button
                key={ch.id}
                type="button"
                className={ch.id === characterId ? "chip active" : "chip"}
                title={ch.description}
                onClick={() =>
                  onAvatarChange({
                    pack_id: pack?.id || packId,
                    character_id: ch.id,
                    gender:
                      (ch.genders.includes(gender)
                        ? gender
                        : (ch.default_gender as typeof gender)) || "neutral",
                  })
                }
              >
                {CHARACTER_EMOJI[ch.id] ? `${CHARACTER_EMOJI[ch.id]} ` : ""}
                {ch.name}
              </button>
            ))}
          </div>
          <div className="gender-row">
            {(["boy", "girl", "neutral"] as const).map((g) => (
              <button
                key={g}
                type="button"
                className={gender === g ? "chip active" : "chip"}
                onClick={() =>
                  onAvatarChange({
                    pack_id: pack?.id || packId,
                    character_id: characterId,
                    gender: g,
                  })
                }
              >
                {GENDER_LABEL[g]}
              </button>
            ))}
          </div>
        </div>

        <div className="section">
          <h3>Games</h3>
          {activeGame ? (
            <>
              <p className="game-prompt">{activeGame.prompt}</p>
              <button type="button" className="chip" onClick={onCancelGame}>
                End game
              </button>
            </>
          ) : (
            <div className="kid-menu-grid">
              {games.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  className="menu-tile"
                  onClick={() => {
                    onStartGame(g.id);
                    onClose();
                  }}
                >
                  <span className="tile-emoji">{GAME_EMOJI[g.id] || "🎲"}</span>
                  {g.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="section">
          <h3>Talk button</h3>
          <button
            type="button"
            className={capturing ? "key-capture capturing" : "key-capture"}
            onClick={() => setCapturing(true)}
          >
            {capturing ? "Press a key…" : `Hold ${keyLabel(pttKey)} to talk`}
          </button>
          {pttKey !== DEFAULT_PTT_KEY ? (
            <button type="button" className="ghost" onClick={() => onSetPttKey(DEFAULT_PTT_KEY)}>
              Reset to Space
            </button>
          ) : null}
        </div>

        {showKidSwitch ? (
          <button
            type="button"
            className="menu-tile"
            onClick={() => {
              onClose();
              onSwitchKid();
            }}
          >
            <span className="tile-emoji">👥</span>
            Who is playing?
          </button>
        ) : null}

        {usage?.limit_minutes ? (
          <p className="hint">
            Play time today: {Math.round(usage.used_minutes ?? 0)} / {usage.limit_minutes} min
            {usage.over_limit ? " · all done for today!" : ""}
          </p>
        ) : null}

        <button type="button" className="grownups-btn" onClick={onOpenParent}>
          🔒 Grown-ups (PIN)
        </button>
      </div>
    </div>
  );
}
