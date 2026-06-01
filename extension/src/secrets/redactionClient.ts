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
// OpenRouter `sk-...` style bearer keys.
const REDACTION_PATTERNS: RegExp[] = [
  /(api[_-]?key\s*[=:]\s*)\S+/gi,
  /(password\s*[=:]\s*)\S+/gi,
  /(token\s*[=:]\s*)\S+/gi,
  /(secret\s*[=:]\s*)\S+/gi,
  /\bsk-[A-Za-z0-9-]{8,}\b/g,
  /\bBearer\s+[A-Za-z0-9._-]{8,}\b/gi,
];

/** Redact secret-shaped substrings, preserving the leading key/label. */
export function redactSecrets(input: string): string {
  let output = input;
  for (const pattern of REDACTION_PATTERNS) {
    output = output.replace(pattern, (match, prefix?: string) =>
      prefix ? `${prefix}${REDACTION_PLACEHOLDER}` : REDACTION_PLACEHOLDER
    );
  }
  return output;
}
