// Design tokens — single source of truth for all colour values.
// Every component imports from here; no hex literals in component files.

export const C = {
  bgPage:        '#F5F4F0',
  bgSurface:     '#FFFFFF',
  bgMuted:       '#FAFAF8',
  bgStatsrow:    '#F5F4F0',

  topbar:        '#1C1C1A',
  topbarText:    '#F5F4F0',

  accent:        '#0F6E56',
  accentDark:    '#085041',
  accentLight:   '#E1F5EE',

  border:        '#E2DED8',
  borderLight:   '#F0EDE8',

  textPrimary:   '#1C1C1A',
  textSecondary: '#6B6860',
  textMuted:     '#9B9890',

  // Verdict / severity
  severeBg:      '#FCEBEB',
  severeBorder:  '#F7C1C1',
  severeText:    '#791F1F',

  flaggedBg:     '#FAEEDA',
  flaggedBorder: '#FAC775',
  flaggedText:   '#633806',

  cleanBg:       '#EAF3DE',
  cleanBorder:   '#C0DD97',
  cleanText:     '#27500A',

  // Detection layer badges — LLM (blue), REGEX (warm grey), MANUAL (purple)
  regexBg:       '#F1EFE8',
  regexText:     '#444441',
  regexBorder:   '#D4D0C9',

  llmBg:         '#E6F1FB',
  llmText:       '#0C447C',
  llmBorder:     '#B5D4F4',

  manualBg:      '#EEEDFE',
  manualBorder:  '#AFA9EC',
  manualText:    '#3C3489',

  // Session type pills — Chat (blue) and Voice (purple)
  chatBg:        '#E6F1FB',
  chatText:      '#0C447C',
  chatBorder:    '#B5D4F4',

  voiceBg:       '#EEEDFE',
  voiceText:     '#3C3489',
  voiceBorder:   '#AFA9EC',
};

// Reusable font-family strings
export const MONO = "'DM Mono', monospace";
export const SANS = "'DM Sans', sans-serif";

// ---------------------------------------------------------------------------
// Uppercase named exports — aliases for every C property
// ---------------------------------------------------------------------------

export const SEVERE_BG     = C.severeBg;
export const SEVERE_BORDER = C.severeBorder;
export const SEVERE_TEXT   = C.severeText;

export const FLAGGED_BG     = C.flaggedBg;
export const FLAGGED_BORDER = C.flaggedBorder;
export const FLAGGED_TEXT   = C.flaggedText;

export const CLEAN_BG     = C.cleanBg;
export const CLEAN_BORDER = C.cleanBorder;
export const CLEAN_TEXT   = C.cleanText;

export const ACCENT       = C.accent;
export const ACCENT_DARK  = C.accentDark;
export const ACCENT_LIGHT = C.accentLight;

export const BG_PAGE     = C.bgPage;
export const BG_SURFACE  = C.bgSurface;
export const BG_MUTED    = C.bgMuted;
export const BG_STATSROW = C.bgStatsrow;

export const TEXT_PRIMARY   = C.textPrimary;
export const TEXT_SECONDARY = C.textSecondary;
export const TEXT_MUTED     = C.textMuted;

export const BORDER       = C.border;
export const BORDER_LIGHT = C.borderLight;

export const TOPBAR = C.topbar;

export const MANUAL_BG     = C.manualBg;
export const MANUAL_BORDER = C.manualBorder;
export const MANUAL_TEXT   = C.manualText;

export const CHAT_BG     = C.chatBg;
export const CHAT_TEXT   = C.chatText;
export const CHAT_BORDER = C.chatBorder;

export const VOICE_BG     = C.voiceBg;
export const VOICE_TEXT   = C.voiceText;
export const VOICE_BORDER = C.voiceBorder;
