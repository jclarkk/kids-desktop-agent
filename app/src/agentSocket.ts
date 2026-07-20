export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

export type AgentState = {
  type?: string;
  ai_mode?: string;
  avatar?: {
    pack_id: string;
    character_id: string;
    gender: "boy" | "girl" | "neutral";
    wake_word: string;
  };
  voice_id?: string;
  avatar_packs?: Array<{
    id: string;
    name: string;
    characters: Array<{
      id: string;
      name: string;
      description?: string;
      genders: Array<"boy" | "girl" | "neutral">;
      default_gender?: string;
      voices?: Record<string, string>;
    }>;
  }>;
  kids?: Array<{
    id: string;
    name: string;
    age: number;
    preferred_avatar?: string;
    preferred_gender?: string;
    daily_limit_minutes?: number;
    english_level?: "beginner" | "elementary" | "intermediate";
    face_preview?: string;
    voice_enrolled?: boolean;
    face_enrolled?: boolean;
  }>;
  active_kid_id?: string | null;
  needs_parent_setup?: boolean;
  needs_who_is_playing?: boolean;
  identity?: {
    require_who_is_playing?: boolean;
    voice_name_match?: boolean;
    face_match?: boolean;
    allow_tap_select?: boolean;
    face_match_threshold?: number;
  };
  usage?: {
    kid_id?: string | null;
    used_minutes?: number;
    limit_minutes?: number;
    remaining_minutes?: number;
    over_limit?: boolean;
  };
  game?: { kind: string; prompt: string; hint?: string } | null;
  games_available?: Array<{ id: string; label: string }>;
  skills_enabled?: string[];
  has_api_key?: boolean;
  chat_model?: string;
  local_model?: string;
  local_catalog?: Array<{
    id: string;
    label: string;
    ollama: string;
    fit: string;
    notes?: string;
  }>;
  hardware?: {
    vram_gb?: number | null;
    gpu_name?: string | null;
    ollama_ok?: boolean;
    ollama_models?: string[];
  };
  budget?: {
    spent_usd?: number;
    limit_usd?: number;
    remaining_usd?: number;
  };
  computer_use_mode?: string;
  computer_use?: {
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
  speech?: {
    stt?: string;
    tts?: string;
    wake_word?: boolean;
    notes?: string[];
  };
};

export type AssistantReply = {
  type: "assistant_reply";
  user_transcript: string;
  text: string;
  error?: string | null;
};

const DEFAULT_URL =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_WS_URL) ||
  "ws://127.0.0.1:8765";

export class AgentSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private onMessage: (data: Record<string, unknown>) => void;
  private onStatus: (status: "connecting" | "open" | "closed") => void;

  constructor(
    onMessage: (data: Record<string, unknown>) => void,
    onStatus: (status: "connecting" | "open" | "closed") => void,
    url = DEFAULT_URL
  ) {
    this.onMessage = onMessage;
    this.onStatus = onStatus;
    this.url = url;
  }

  connect() {
    this.onStatus("connecting");
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => this.onStatus("open");
    this.ws.onclose = () => {
      this.onStatus("closed");
      window.setTimeout(() => this.connect(), 1500);
    };
    this.ws.onerror = () => this.ws?.close();
    this.ws.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(String(ev.data)) as Record<string, unknown>);
      } catch {
        /* ignore */
      }
    };
  }

  send(payload: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  close() {
    this.ws?.close();
  }
}
