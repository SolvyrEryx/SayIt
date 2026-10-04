/**
 * Feature content. Every item corresponds to functionality documented as
 * implemented in the desktop application's README. Anything not implemented
 * is not listed — and nothing here may use unsupported marketing claims.
 */

export type FeatureItem = {
  title: string;
  body: string;
  kbd?: string[];
};

export type FeatureSection = {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  items: FeatureItem[];
};

export const FEATURE_SECTIONS: FeatureSection[] = [
  {
    id: "dictation",
    eyebrow: "Core",
    title: "Voice dictation",
    description:
      "The foundation: hold a key, speak, release. Recognition runs on your machine, and the result lands where you were typing.",
    items: [
      {
        title: "Push-to-talk recording",
        body: "Hold a configurable global hotkey to record; release to transcribe. Press Esc to cancel mid-recording or while transcription is running.",
        kbd: ["Ctrl", "Space"],
      },
      {
        title: "Local speech recognition",
        body: "Transcription runs on your device via Sherpa-ONNX once a model is installed. Decoding happens once, after you release — SayIt is not a streaming dictation system.",
      },
      {
        title: "Text at your cursor",
        body: "The transcript is inserted into the app you were typing in, at the cursor. If insertion fails, the text stays recoverable instead of being lost.",
      },
    ],
  },
  {
    id: "context",
    eyebrow: "Awareness",
    title: "Context awareness",
    description:
      "SayIt looks at which application is active — using process and window metadata only — and picks a formatting profile.",
    items: [
      {
        title: "Formatting profiles",
        body: "Profiles adjust which local correction rules run: Developer, Email, Chat, Notes, Prompt, or Normal. A profile never rewrites your words, and a manual override always wins.",
      },
      {
        title: "Metadata only",
        body: "Context detection reads no screenshots, no clipboard contents, no keystrokes, and no page or editor contents — just the application's own metadata.",
      },
    ],
  },
  {
    id: "intelligence",
    eyebrow: "Deterministic",
    title: "Local intelligence",
    description:
      "A local-first intelligence layer on top of dictation. It uses no LLM and no network — identical input, context, and settings always produce the same output, and every feature can be turned off.",
    items: [
      {
        title: "Technical correction",
        body: "Normalizes common developer terms (\"git hub\" → GitHub, \"ci slash cd\" → CI/CD) and formats clearly-dictated URLs, file paths, email addresses, and API/version structures. Conservative by design — ordinary prose is left alone — and it can be turned off.",
      },
      {
        title: "Voice edit",
        body: "\"I'll arrive at five. Actually six.\" becomes \"I'll arrive at six.\" Also \"scratch that\", \"replace five with six\", and \"delete the last sentence\". Ambiguous phrases stay ordinary text.",
      },
      {
        title: "Snippets",
        body: "Say a trigger like \"my github\" to insert a saved block of text. Snippets are text only — content like git pull is inserted as literal text and never executed.",
      },
      {
        title: "Developer mode",
        body: "\"get user by id, camel case\" becomes getUserById — plus snake, kebab, and pascal casing, and a spoken code-block wrapper for longer passages.",
      },
      {
        title: "Safe zones",
        body: "Designate protected applications — password managers, banking — where recording is blocked before any audio is captured.",
      },
      {
        title: "Remember corrections",
        body: "When you fix a transcript, SayIt can offer to remember the fix. Only an explicit \"Remember\" creates a rule; there is no silent learning.",
      },
      {
        title: "Structure commands",
        body: "\"New line\" and \"new paragraph\" become real breaks, and clean ordinal dictation (\"first … second … third …\") becomes a proper list.",
      },
    ],
  },
  {
    id: "personalization",
    eyebrow: "Yours",
    title: "Personalization",
    description: "You control the words SayIt knows — nothing is learned without you.",
    items: [
      {
        title: "Custom vocabulary",
        body: "Spoken-form → written-form mappings you create yourself: \"next js\" → Next.js, \"open ai\" → OpenAI. Case-insensitive, multi-word, longest-match-first; entries can be edited, categorized, and individually disabled.",
      },
    ],
  },
];

/** Honest boundaries of the current implementation, shown on /features. */
export const HONEST_LIMITATIONS: string[] = [
  "Not streaming: transcription happens once, after you release the hotkey — partial words are not transcribed while you speak.",
  "Insertion depends on a focused editable text field; paste success cannot be conclusively verified, and your previous clipboard contents may not be restored.",
  "Linux is partially supported and less validated; global hotkeys may require X11 and may not work under Wayland.",
  "Speech models are separate downloads from the application — roughly 100 MB to 1 GB depending on the model.",
  "Speed varies with your hardware, utterance length, and model choice — no fixed numbers are claimed.",
];
