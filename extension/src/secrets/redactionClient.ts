// Client-side secret redaction for logs and chat output.
//
// Slice 4 deliverable (spec NFR-SC-003, §6.4 Secret Redaction Rules). A pure,
// defensive redaction pass applied before the extension writes anything to its
// output channel or renders it in chat, so an API key or token never surfaces in
// the UI. The authoritative redaction happens runtime-side (Slice 6
// `security/redaction.py`); this mirrors the same rule families as a second line
// of defense. Kept free of the VS Code API for unit-testability.

export const REDACTION_PLACEHOLDER = "***REDACTED***";

// Mirrors the spec §6.4 rule families: api keys, passwords, tokens, secrets, and
// OpenRouter `sk-...` style bearer keys. The quoted variants catch JSON bodies
// (`"api_key": "..."`), which the plain assignment shape misses because of the
// closing quote between the key and the colon.
const SENSITIVE = "(?:api[_-]?key|apikey|password|passwd|token|secret)";
const REDACTION_RULES: Array<{ pattern: RegExp; replacement: string }> = [
  {
    pattern: new RegExp(`("${SENSITIVE}"\\s*:\\s*")[^"]*(")`, "gi"),
    replacement: `$1${REDACTION_PLACEHOLDER}$2`,
  },
  {
    pattern: new RegExp(`('${SENSITIVE}'\\s*:\\s*')[^']*(')`, "gi"),
    replacement: `$1${REDACTION_PLACEHOLDER}$2`,
  },
  {
    pattern: new RegExp(`(${SENSITIVE}\\s*[=:]\\s*)("[^"]*"|'[^']*'|\\S+)`, "gi"),
    replacement: `$1${REDACTION_PLACEHOLDER}`,
  },
  { pattern: /\bsk-[A-Za-z0-9-]{8,}\b/g, replacement: REDACTION_PLACEHOLDER },
  {
    pattern: /\bBearer\s+[A-Za-z0-9._-]{8,}\b/gi,
    replacement: `Bearer ${REDACTION_PLACEHOLDER}`,
  },
  {
    pattern: /\bBasic\s+[A-Za-z0-9+/=]{8,}\b/g,
    replacement: `Basic ${REDACTION_PLACEHOLDER}`,
  },
  { pattern: /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g, replacement: REDACTION_PLACEHOLDER },
  { pattern: /\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, replacement: REDACTION_PLACEHOLDER },
  { pattern: /\bAKIA[0-9A-Z]{16}\b/g, replacement: REDACTION_PLACEHOLDER },
  { pattern: /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, replacement: REDACTION_PLACEHOLDER },
];

/** Redact secret-shaped substrings, preserving the leading key/label. */
export function redactSecrets(input: string): string {
  let output = input;
  for (const { pattern, replacement } of REDACTION_RULES) {
    output = output.replace(pattern, replacement);
  }
  return output;
}
