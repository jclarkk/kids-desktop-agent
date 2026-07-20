export type EnglishLevel = "beginner" | "elementary" | "intermediate";

/** Short, very simple questions for kids with little English. */
const BEGINNER_QUESTIONS = [
  "Tell me a joke!",
  "What color is the sun?",
  "How do you say cat?",
  "Sing a song!",
  "What animal is big?",
  "What is a dog?",
  "Count to ten!",
];

/** Curious-kid questions for kids with more English. */
const BIG_KID_QUESTIONS = [
  "Why is the sky blue?",
  "Tell me a joke!",
  "How do planes fly?",
  "What did dinosaurs eat?",
  "Why do cats purr?",
  "How deep is the ocean?",
  "What is the biggest animal?",
  "Why do we dream?",
  "How do rainbows happen?",
  "What is space like?",
  "Why do birds sing?",
  "How do fish breathe?",
];

const BEGINNER_NUDGES = [
  "You can ask me anything! Tap a question!",
  "Ask me a question! Tap one!",
];

const BIG_KID_NUDGES = [
  "Psst — you can ask me anything! Need an idea? Tap a question.",
  "I love questions! Ask me anything, or tap one of these.",
  "Wondering about something? You can ask me anything!",
];

function sample<T>(pool: T[], count: number): T[] {
  const copy = [...pool];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, count);
}

export function pickSuggestions(level: EnglishLevel, count = 3): string[] {
  const pool = level === "beginner" ? BEGINNER_QUESTIONS : BIG_KID_QUESTIONS;
  return sample(pool, count);
}

export function pickNudgeLine(level: EnglishLevel): string {
  const pool = level === "beginner" ? BEGINNER_NUDGES : BIG_KID_NUDGES;
  return pool[Math.floor(Math.random() * pool.length)];
}
