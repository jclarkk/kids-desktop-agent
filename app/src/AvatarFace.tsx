import type { AvatarState } from "./agentSocket";

/** Emoji used wherever a character is listed (onboarding, kid menu). */
export const CHARACTER_EMOJI: Record<string, string> = {
  sparky: "⭐",
  pixel: "🤖",
  luna: "🌙",
  rosie: "👑",
  blaze: "🦸",
  sparkle: "🦄",
  astro: "🚀",
  finn: "🦜",
  flora: "🧚",
  rex: "🦖",
  marina: "🧜",
  ember: "🐉",
};

const LABELS: Record<AvatarState, string> = {
  idle: "Tap & hold to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

type Props = {
  characterId: string;
  state: AvatarState;
  onPressStart: () => void;
  onPressEnd: () => void;
};

function CharacterArt({ characterId, state }: { characterId: string; state: AvatarState }) {
  if (characterId === "pixel") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        <rect x="30" y="40" width="100" height="90" rx="18" fill="#6BCF7F" />
        <rect x="48" y="62" width="24" height="24" rx="6" fill="#fff" />
        <rect x="88" y="62" width="24" height="24" rx="6" fill="#fff" />
        <circle cx="60" cy="74" r="6" fill="#2F4858" className={state === "thinking" ? "blink" : ""} />
        <circle cx="100" cy="74" r="6" fill="#2F4858" className={state === "thinking" ? "blink" : ""} />
        <rect
          x="62"
          y="100"
          width="36"
          height={state === "speaking" ? 16 : 8}
          rx="6"
          fill="#2F4858"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        <rect x="70" y="24" width="20" height="20" fill="#2F4858" />
        <circle cx="80" cy="20" r="8" fill="#F4C95F" />
      </svg>
    );
  }
  if (characterId === "luna") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        <circle cx="80" cy="82" r="52" fill="#C9B6FF" />
        <circle cx="98" cy="70" r="40" fill="#4A3F6B" opacity="0.25" />
        <circle cx="62" cy="78" r="7" fill="#4A3F6B" />
        <circle cx="98" cy="78" r="7" fill="#4A3F6B" />
        <path
          d={state === "speaking" ? "M60 108 Q80 128 100 108" : "M60 110 Q80 118 100 110"}
          fill="none"
          stroke="#4A3F6B"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <circle cx="118" cy="40" r="10" fill="#FFF6A8" />
      </svg>
    );
  }
  if (characterId === "rosie") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* hair */}
        <path d="M28 92 Q22 40 80 34 Q138 40 132 92 Q132 120 118 128 L118 84 Q118 56 80 54 Q42 56 42 84 L42 128 Q28 120 28 92 Z" fill="#8A5A3B" />
        {/* face */}
        <circle cx="80" cy="90" r="40" fill="#FBD7B8" />
        {/* crown */}
        <path d="M52 46 L58 26 L70 40 L80 20 L90 40 L102 26 L108 46 Z" fill="#E8C45A" stroke="#C99B2E" strokeWidth="3" strokeLinejoin="round" />
        <circle cx="80" cy="32" r="4" fill="#F7A8C4" />
        <circle cx="60" cy="40" r="3" fill="#7FD1E8" />
        <circle cx="100" cy="40" r="3" fill="#7FD1E8" />
        {/* eyes */}
        <circle cx="66" cy="86" r="6" fill="#4A3324" className={state === "thinking" ? "blink" : ""} />
        <circle cx="94" cy="86" r="6" fill="#4A3324" className={state === "thinking" ? "blink" : ""} />
        <path d="M58 76 Q66 72 72 76" fill="none" stroke="#4A3324" strokeWidth="3" strokeLinecap="round" />
        <path d="M88 76 Q94 72 102 76" fill="none" stroke="#4A3324" strokeWidth="3" strokeLinecap="round" />
        {/* blush */}
        <circle cx="56" cy="100" r="7" fill="#F7A8C4" opacity="0.6" />
        <circle cx="104" cy="100" r="7" fill="#F7A8C4" opacity="0.6" />
        {/* mouth */}
        <path
          d={state === "speaking" ? "M68 108 Q80 124 92 108" : "M68 110 Q80 118 92 110"}
          fill={state === "speaking" ? "#B85C7A" : "none"}
          stroke="#B85C7A"
          strokeWidth="5"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
      </svg>
    );
  }
  if (characterId === "blaze") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* cape */}
        <path d="M36 100 Q30 148 46 150 L80 128 L114 150 Q130 148 124 100 Z" fill="#E2643B" />
        {/* head */}
        <circle cx="80" cy="82" r="44" fill="#F6C9A0" />
        {/* hair swoosh */}
        <path d="M40 68 Q50 34 84 38 Q118 42 120 68 Q108 52 84 52 Q56 52 40 68 Z" fill="#3B3B4F" />
        {/* mask */}
        <path d="M40 74 Q80 62 120 74 L118 94 Q80 86 42 94 Z" fill="#4C7DE0" />
        <ellipse cx="63" cy="82" rx="9" ry="7" fill="#fff" />
        <ellipse cx="97" cy="82" rx="9" ry="7" fill="#fff" />
        <circle cx="63" cy="82" r="4" fill="#1c2b33" className={state === "thinking" ? "blink" : ""} />
        <circle cx="97" cy="82" r="4" fill="#1c2b33" className={state === "thinking" ? "blink" : ""} />
        {/* chest star */}
        <polygon points="80,132 84,142 95,142 86,148 90,158 80,151 70,158 74,148 65,142 76,142" fill="#F4C95F" />
        {/* mouth */}
        <path
          d={state === "speaking" ? "M66 104 Q80 120 94 104" : "M66 106 Q80 114 94 106"}
          fill={state === "speaking" ? "#8A4A3B" : "none"}
          stroke="#8A4A3B"
          strokeWidth="5"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
      </svg>
    );
  }
  if (characterId === "sparkle") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* mane */}
        <path d="M46 44 Q30 70 36 104 Q28 84 30 62 Q34 48 46 44 Z" fill="#B87FD9" />
        <path d="M50 40 Q38 78 46 116 Q34 92 38 60 Q42 46 50 40 Z" fill="#7FD1E8" />
        {/* ears */}
        <path d="M52 40 L60 18 L72 38 Z" fill="#F3EDFF" stroke="#B87FD9" strokeWidth="3" strokeLinejoin="round" />
        <path d="M92 36 L104 16 L112 38 Z" fill="#F3EDFF" stroke="#B87FD9" strokeWidth="3" strokeLinejoin="round" />
        {/* horn */}
        <path d="M78 34 L84 4 L92 34 Z" fill="#E8C45A" stroke="#C99B2E" strokeWidth="3" strokeLinejoin="round" />
        {/* head */}
        <circle cx="82" cy="86" r="46" fill="#F3EDFF" stroke="#E3D6F7" strokeWidth="3" />
        {/* forelock */}
        <path d="M62 46 Q84 34 106 48 Q94 56 82 54 Q70 54 62 46 Z" fill="#F7A8C4" />
        {/* eyes */}
        <circle cx="66" cy="84" r="7" fill="#5B4A7A" className={state === "thinking" ? "blink" : ""} />
        <circle cx="98" cy="84" r="7" fill="#5B4A7A" className={state === "thinking" ? "blink" : ""} />
        <circle cx="68" cy="82" r="2" fill="#fff" />
        <circle cx="100" cy="82" r="2" fill="#fff" />
        {/* snout + mouth */}
        <ellipse cx="82" cy="112" rx="20" ry="14" fill="#FBE3F0" />
        <path
          d={state === "speaking" ? "M72 110 Q82 122 92 110" : "M72 112 Q82 118 92 112"}
          fill="none"
          stroke="#B87FD9"
          strokeWidth="4"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        {/* sparkles */}
        <path d="M128 44 L131 52 L139 55 L131 58 L128 66 L125 58 L117 55 L125 52 Z" fill="#F4C95F" />
        <circle cx="120" cy="30" r="3" fill="#7FD1E8" />
      </svg>
    );
  }
  if (characterId === "astro") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* stars */}
        <circle cx="24" cy="34" r="3" fill="#F4C95F" />
        <circle cx="140" cy="52" r="2.5" fill="#7FD1E8" />
        <path d="M132 20 L134 26 L140 28 L134 30 L132 36 L130 30 L124 28 L130 26 Z" fill="#F4C95F" />
        {/* suit collar */}
        <path d="M44 122 Q80 108 116 122 L116 150 L44 150 Z" fill="#E2833B" />
        <rect x="70" y="126" width="20" height="10" rx="4" fill="#EAF2F8" />
        {/* helmet */}
        <circle cx="80" cy="76" r="50" fill="#EAF2F8" stroke="#C8D8E4" strokeWidth="4" />
        <circle cx="80" cy="78" r="38" fill="#BFE3F2" />
        {/* face (medium-dark skin) */}
        <circle cx="80" cy="82" r="32" fill="#C68B59" />
        <path d="M54 66 Q66 52 80 54 Q94 52 106 66 Q94 60 80 60 Q66 60 54 66 Z" fill="#2E2A26" />
        <circle cx="68" cy="82" r="6" fill="#2E2A26" className={state === "thinking" ? "blink" : ""} />
        <circle cx="92" cy="82" r="6" fill="#2E2A26" className={state === "thinking" ? "blink" : ""} />
        <path
          d={state === "speaking" ? "M68 98 Q80 112 92 98" : "M68 100 Q80 106 92 100"}
          fill={state === "speaking" ? "#6B3F28" : "none"}
          stroke="#6B3F28"
          strokeWidth="4"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        {/* helmet shine */}
        <path d="M46 56 Q54 42 70 38" fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round" opacity="0.7" />
      </svg>
    );
  }
  if (characterId === "finn") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* face (medium skin) */}
        <circle cx="76" cy="90" r="42" fill="#B07B4F" />
        {/* bandana */}
        <path d="M34 78 Q40 42 76 40 Q112 42 118 78 Q98 66 76 66 Q54 66 34 78 Z" fill="#D8544F" />
        <circle cx="52" cy="52" r="4" fill="#fff" opacity="0.8" />
        <circle cx="76" cy="46" r="4" fill="#fff" opacity="0.8" />
        <circle cx="100" cy="52" r="4" fill="#fff" opacity="0.8" />
        <path d="M116 72 L134 60 L130 80 Z" fill="#D8544F" />
        {/* gold earring */}
        <circle cx="38" cy="102" r="6" fill="none" stroke="#F4C95F" strokeWidth="3" />
        {/* eyes */}
        <circle cx="62" cy="88" r="6" fill="#2E2015" className={state === "thinking" ? "blink" : ""} />
        <circle cx="90" cy="88" r="6" fill="#2E2015" className={state === "thinking" ? "blink" : ""} />
        <path d="M54 78 Q62 74 68 78" fill="none" stroke="#2E2015" strokeWidth="3" strokeLinecap="round" />
        <path d="M84 78 Q90 74 98 78" fill="none" stroke="#2E2015" strokeWidth="3" strokeLinecap="round" />
        {/* big grin */}
        <path
          d={state === "speaking" ? "M58 108 Q76 128 94 108" : "M58 110 Q76 120 94 110"}
          fill={state === "speaking" ? "#5C3320" : "none"}
          stroke="#5C3320"
          strokeWidth="5"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        {/* parrot pal */}
        <ellipse cx="132" cy="112" rx="12" ry="16" fill="#4BB05C" />
        <circle cx="132" cy="98" r="9" fill="#E2643B" />
        <circle cx="135" cy="96" r="2" fill="#1c2b33" />
        <path d="M141 98 L150 100 L141 104 Z" fill="#F4C95F" />
        <path d="M126 122 Q132 132 138 122" fill="none" stroke="#2F8F46" strokeWidth="3" strokeLinecap="round" />
      </svg>
    );
  }
  if (characterId === "flora") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* wings */}
        <ellipse cx="34" cy="84" rx="20" ry="34" fill="#BFE3F2" opacity="0.8" transform="rotate(-14 34 84)" />
        <ellipse cx="126" cy="84" rx="20" ry="34" fill="#BFE3F2" opacity="0.8" transform="rotate(14 126 84)" />
        <ellipse cx="38" cy="110" rx="12" ry="18" fill="#D8B4F8" opacity="0.8" transform="rotate(-20 38 110)" />
        <ellipse cx="122" cy="110" rx="12" ry="18" fill="#D8B4F8" opacity="0.8" transform="rotate(20 122 110)" />
        {/* hair puffs */}
        <circle cx="52" cy="58" r="16" fill="#2E2126" />
        <circle cx="80" cy="48" r="18" fill="#2E2126" />
        <circle cx="108" cy="58" r="16" fill="#2E2126" />
        {/* face (deep skin) */}
        <circle cx="80" cy="90" r="38" fill="#8D5A3C" />
        {/* flower crown */}
        <circle cx="58" cy="56" r="6" fill="#F7A8C4" />
        <circle cx="80" cy="48" r="6" fill="#F4C95F" />
        <circle cx="102" cy="56" r="6" fill="#F7A8C4" />
        <circle cx="58" cy="56" r="2.5" fill="#fff" />
        <circle cx="80" cy="48" r="2.5" fill="#fff" />
        <circle cx="102" cy="56" r="2.5" fill="#fff" />
        {/* eyes */}
        <circle cx="66" cy="88" r="6" fill="#251A12" className={state === "thinking" ? "blink" : ""} />
        <circle cx="94" cy="88" r="6" fill="#251A12" className={state === "thinking" ? "blink" : ""} />
        <path d="M58 78 Q66 74 72 78" fill="none" stroke="#251A12" strokeWidth="3" strokeLinecap="round" />
        <path d="M88 78 Q94 74 102 78" fill="none" stroke="#251A12" strokeWidth="3" strokeLinecap="round" />
        {/* blush */}
        <circle cx="58" cy="100" r="6" fill="#C97B63" opacity="0.7" />
        <circle cx="102" cy="100" r="6" fill="#C97B63" opacity="0.7" />
        {/* mouth */}
        <path
          d={state === "speaking" ? "M68 106 Q80 120 92 106" : "M68 108 Q80 115 92 108"}
          fill={state === "speaking" ? "#5C3324" : "none"}
          stroke="#5C3324"
          strokeWidth="4"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        {/* sparkle */}
        <path d="M130 40 L133 48 L141 51 L133 54 L130 62 L127 54 L119 51 L127 48 Z" fill="#F4C95F" />
      </svg>
    );
  }
  if (characterId === "rex") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* back spikes */}
        <path d="M48 44 L58 24 L68 44 Z" fill="#2F8F46" />
        <path d="M72 38 L82 16 L92 38 Z" fill="#2F8F46" />
        <path d="M96 44 L106 24 L116 44 Z" fill="#2F8F46" />
        {/* head */}
        <rect x="34" y="40" width="92" height="76" rx="34" fill="#6BCF7F" />
        {/* snout */}
        <rect x="52" y="92" width="72" height="44" rx="20" fill="#8FDCA0" />
        <circle cx="70" cy="106" r="4" fill="#2F8F46" />
        <circle cx="94" cy="106" r="4" fill="#2F8F46" />
        {/* eyes */}
        <ellipse cx="62" cy="72" rx="10" ry="11" fill="#fff" />
        <ellipse cx="98" cy="72" rx="10" ry="11" fill="#fff" />
        <circle cx="64" cy="74" r="5" fill="#1c3b28" className={state === "thinking" ? "blink" : ""} />
        <circle cx="96" cy="74" r="5" fill="#1c3b28" className={state === "thinking" ? "blink" : ""} />
        {/* mouth with friendly teeth */}
        <path
          d={state === "speaking" ? "M64 120 Q88 136 112 120" : "M64 122 Q88 130 112 122"}
          fill={state === "speaking" ? "#2F6B3C" : "none"}
          stroke="#2F6B3C"
          strokeWidth="5"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        <path d="M74 121 L78 127 L82 121 Z" fill="#fff" />
        <path d="M96 121 L100 127 L104 121 Z" fill="#fff" />
      </svg>
    );
  }
  if (characterId === "marina") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* waves */}
        <path d="M12 138 Q28 128 44 138 Q60 148 76 138 Q92 128 108 138 Q124 148 148 138" fill="none" stroke="#7FD1E8" strokeWidth="6" strokeLinecap="round" opacity="0.7" />
        {/* flowing hair */}
        <path d="M36 96 Q26 46 80 38 Q134 46 124 96 Q130 118 118 130 Q122 100 112 78 Q98 60 80 60 Q62 60 48 78 Q38 100 42 130 Q30 118 36 96 Z" fill="#5A3B8C" />
        {/* face (warm medium skin) */}
        <circle cx="80" cy="88" r="36" fill="#C99268" />
        {/* shell crown */}
        <path d="M66 46 Q72 32 80 30 Q88 32 94 46 Q87 42 80 42 Q73 42 66 46 Z" fill="#F7A8C4" stroke="#DE7BA4" strokeWidth="2" />
        <path d="M80 30 L80 42 M72 34 L75 44 M88 34 L85 44" stroke="#DE7BA4" strokeWidth="2" strokeLinecap="round" />
        {/* eyes */}
        <circle cx="66" cy="86" r="6" fill="#3A2618" className={state === "thinking" ? "blink" : ""} />
        <circle cx="94" cy="86" r="6" fill="#3A2618" className={state === "thinking" ? "blink" : ""} />
        <path d="M58 76 Q66 72 72 76" fill="none" stroke="#3A2618" strokeWidth="3" strokeLinecap="round" />
        <path d="M88 76 Q94 72 102 76" fill="none" stroke="#3A2618" strokeWidth="3" strokeLinecap="round" />
        {/* blush */}
        <circle cx="58" cy="98" r="6" fill="#E28B6D" opacity="0.6" />
        <circle cx="102" cy="98" r="6" fill="#E28B6D" opacity="0.6" />
        {/* mouth */}
        <path
          d={state === "speaking" ? "M68 104 Q80 118 92 104" : "M68 106 Q80 113 92 106"}
          fill={state === "speaking" ? "#7A4630" : "none"}
          stroke="#7A4630"
          strokeWidth="4"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        {/* pearl bubbles */}
        <circle cx="132" cy="60" r="4" fill="#BFE3F2" />
        <circle cx="140" cy="46" r="3" fill="#BFE3F2" />
      </svg>
    );
  }
  if (characterId === "ember") {
    return (
      <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
        {/* horns */}
        <path d="M50 42 Q44 22 58 18 Q56 34 62 42 Z" fill="#F4C95F" />
        <path d="M110 42 Q116 22 102 18 Q104 34 98 42 Z" fill="#F4C95F" />
        {/* ears/frills */}
        <ellipse cx="36" cy="76" rx="10" ry="16" fill="#E2643B" transform="rotate(-16 36 76)" />
        <ellipse cx="124" cy="76" rx="10" ry="16" fill="#E2643B" transform="rotate(16 124 76)" />
        {/* head */}
        <circle cx="80" cy="82" r="46" fill="#F2925C" />
        {/* belly patch */}
        <ellipse cx="80" cy="112" rx="26" ry="18" fill="#FCD9A8" />
        {/* eyes */}
        <ellipse cx="64" cy="76" rx="9" ry="10" fill="#fff" />
        <ellipse cx="96" cy="76" rx="9" ry="10" fill="#fff" />
        <circle cx="66" cy="78" r="5" fill="#5C2B1E" className={state === "thinking" ? "blink" : ""} />
        <circle cx="94" cy="78" r="5" fill="#5C2B1E" className={state === "thinking" ? "blink" : ""} />
        {/* nostrils */}
        <circle cx="72" cy="98" r="3" fill="#8F3B2F" />
        <circle cx="88" cy="98" r="3" fill="#8F3B2F" />
        {/* mouth */}
        <path
          d={state === "speaking" ? "M64 110 Q80 124 96 110" : "M64 112 Q80 119 96 112"}
          fill={state === "speaking" ? "#8F3B2F" : "none"}
          stroke="#8F3B2F"
          strokeWidth="4"
          strokeLinecap="round"
          className={state === "speaking" ? "mouth-anim" : ""}
        />
        {/* tiny friendly flame */}
        <path d="M130 118 Q136 108 132 100 Q142 106 140 118 Q138 126 130 126 Q124 122 130 118 Z" fill="#F4C95F" stroke="#E2643B" strokeWidth="2" />
      </svg>
    );
  }
  // sparky (default)
  return (
    <svg viewBox="0 0 160 160" className="avatar-svg" aria-hidden>
      <polygon
        points="80,12 98,58 148,58 108,88 122,138 80,108 38,138 52,88 12,58 62,58"
        fill="#F4C95F"
        stroke="#3A8FB7"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <circle cx="64" cy="78" r="8" fill="#1c2b33" />
      <circle cx="96" cy="78" r="8" fill="#1c2b33" />
      <ellipse
        cx="80"
        cy="104"
        rx="14"
        ry={state === "speaking" ? 12 : 5}
        fill="#1c2b33"
        className={state === "speaking" ? "mouth-anim" : ""}
      />
    </svg>
  );
}

export function AvatarFace({ characterId, state, onPressStart, onPressEnd }: Props) {
  return (
    <button
      type="button"
      className={`avatar-face state-${state}`}
      aria-label={LABELS[state]}
      onMouseDown={onPressStart}
      onMouseUp={onPressEnd}
      onMouseLeave={onPressEnd}
      onTouchStart={(e) => {
        e.preventDefault();
        onPressStart();
      }}
      onTouchEnd={onPressEnd}
    >
      <div className="avatar-orb">
        <CharacterArt characterId={characterId} state={state} />
      </div>
      <p className="avatar-caption">{LABELS[state]}</p>
    </button>
  );
}
