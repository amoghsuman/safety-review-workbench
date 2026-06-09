import React, { useState, useEffect, useRef, useCallback } from 'react';
import { C, MONO } from '../tokens';
import VerdictBadge from './VerdictBadge';
import {
  getSessionDetail, getSessionFlags, submitReview,
  manualFlag, saveSessionNote,
} from '../api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACTIONS = [
  { key: 'CONFIRM',        label: 'Confirm Flag',        active: { bg: C.accent,     color: '#FFFFFF',       border: C.accent       } },
  { key: 'FALSE_POSITIVE', label: 'Mark False Positive', active: { bg: C.flaggedBg,  color: C.flaggedText,   border: C.flaggedBorder } },
  { key: 'ESCALATE',       label: 'Escalate',            active: { bg: C.severeBg,   color: C.severeText,    border: C.severeBorder  } },
  { key: 'CLEAR',          label: 'Clear',               active: { bg: C.bgStatsrow, color: C.textSecondary, border: C.border        } },
];

const STATUS_LABEL = {
  CONFIRMED: 'Confirmed Flag', OVERRIDDEN: 'Marked False Positive',
  ESCALATED: 'Escalated',      REVIEWED:   'Cleared',
};

const INTENT_CATEGORIES = [
  'OFF_PLATFORM_SOLICITATION', 'NSFW', 'FEAR_MANIPULATION',
  'FINANCIAL_SOLICITATION', 'PERSONAL_DATA_COLLECTION',
  'ABUSIVE_LANGUAGE', 'HATE_SPEECH', 'IDENTITY_FRAUD',
  'FAKE_REMEDIES', 'UNAUTHORIZED_MEDICAL_ADVICE',
  'COMPETITOR_PROMOTION', 'OTHER',
];

// ---------------------------------------------------------------------------
// Fuzzy flag → turn association (turn_id primary, word-overlap fallback)
// ---------------------------------------------------------------------------
function buildFlagsByTurnIdx(turns, flags) {
  const result = {};
  flags.forEach((flag) => {
    if (flag.turn_id != null) {
      const idx = flag.turn_id - 1;
      if (idx >= 0 && idx < turns.length) {
        if (!result[idx]) result[idx] = [];
        result[idx].push(flag);
        return;
      }
    }
    if (!flag.reasoning) return;
    const reasonWords = new Set((flag.reasoning.toLowerCase().match(/\b[a-z]{4,}\b/g) || []));
    for (let i = 0; i < turns.length; i++) {
      const tw = (turns[i].message_text || '').toLowerCase().match(/\b[a-z]{4,}\b/g) || [];
      if (tw.some((w) => reasonWords.has(w))) {
        if (!result[i]) result[i] = [];
        result[i].push(flag);
        break;
      }
    }
  });
  return result;
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------
function Skeleton({ width = '100%', height = 14, mt = 0, mb = 0 }) {
  return (
    <div style={{ width, height, marginTop: mt, marginBottom: mb,
      background: C.border, borderRadius: 3, animation: 'pulse 1.5s ease-in-out infinite' }} />
  );
}
function SkeletonPane() {
  return (
    <div style={{ padding: 20 }}>
      <Skeleton width={80} height={10} mb={20} />
      {[75, 60, 85, 50, 70].map((w, i) => (
        <div key={i} style={{ marginBottom: 16 }}><Skeleton width={`${w}%`} height={40} /></div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function Toast({ message }) {
  return (
    <div style={{
      position: 'fixed', bottom: 28, right: 28, background: C.topbar, color: '#FFFFFF',
      borderRadius: 6, padding: '12px 20px', fontSize: 13, display: 'flex',
      alignItems: 'center', gap: 8, zIndex: 1000, animation: 'slideUp 0.25s ease-out',
    }}>
      <span style={{ color: C.accentLight, fontWeight: 600 }}>✓</span>
      {message}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detection-layer badge colours
// ---------------------------------------------------------------------------
function layerStyle(layer) {
  if (layer === 'LLM')    return { bg: C.llmBg,    text: C.llmText,    border: C.llmBorder    };
  if (layer === 'MANUAL') return { bg: C.manualBg, text: C.manualText, border: C.manualBorder };
  return                           { bg: C.regexBg, text: C.regexText,  border: C.regexBorder  };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SessionViewer({ sessionId, sessionList, reviewerName, onBack, onNavigate }) {
  // ── Core state ────────────────────────────────────────────────────────────
  const [data,           setData]           = useState(null);
  const [flags,          setFlags]          = useState([]);   // refreshable separately
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);

  // Review panel state
  const [selectedAction, setSelectedAction] = useState(null);
  const [note,           setNote]           = useState('');
  const [noteFocused,    setNoteFocused]    = useState(false);
  const [submitting,     setSubmitting]     = useState(false);
  const [toast,          setToast]          = useState(null);
  const [showUpdateForm, setShowUpdateForm] = useState(false);

  // Feature 1 — manual flagging
  const [hoveredTurnIdx,    setHoveredTurnIdx]    = useState(null);
  const [openFlagPopover,   setOpenFlagPopover]   = useState(null);
  const [popoverCategory,   setPopoverCategory]   = useState(INTENT_CATEGORIES[0]);
  const [popoverNote,       setPopoverNote]       = useState('');
  const [popoverNoteFocused,setPopoverNoteFocused]= useState(false);
  const [flaggingProgress,  setFlaggingProgress]  = useState(false);
  const [confirmedTurns,    setConfirmedTurns]    = useState(new Set());

  // Feature 2 — session note
  const [sessionNote,       setSessionNote]       = useState('');
  const [sessionNoteFocused,setSessionNoteFocused]= useState(false);
  const [noteSaved,         setNoteSaved]         = useState(false);

  // Refs
  const firstFlaggedRef  = useRef(null);
  const popoverRef       = useRef(null);
  const noteDebounceRef  = useRef(null);

  // ── Data loading ──────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    setFlags([]);
    setNote('');
    setSelectedAction(null);
    setShowUpdateForm(false);
    setSessionNote('');
    setOpenFlagPopover(null);
    setConfirmedTurns(new Set());

    getSessionDetail(sessionId)
      .then((d) => {
        setData(d);
        setFlags(d.flags || []);
        setSessionNote(d.session?.session_note || '');
        setLoading(false);
      })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [sessionId]);

  // Auto-scroll to first flagged turn
  useEffect(() => {
    if (data && firstFlaggedRef.current) {
      firstFlaggedRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [data]);

  // Close popover on outside click or Escape
  useEffect(() => {
    if (openFlagPopover === null) return;
    const onMouseDown = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setOpenFlagPopover(null);
      }
    };
    const onKeyDown = (e) => { if (e.key === 'Escape') setOpenFlagPopover(null); };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openFlagPopover]);

  // ── Navigation ────────────────────────────────────────────────────────────
  const currentIdx = sessionList ? sessionList.findIndex((s) => s.session_id === sessionId) : -1;
  const prevId     = currentIdx > 0                      ? sessionList[currentIdx - 1]?.session_id : null;
  const nextId     = currentIdx < sessionList.length - 1 ? sessionList[currentIdx + 1]?.session_id : null;

  // ── Review submit ─────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (submitting || !selectedAction) return;
    setSubmitting(true);
    try {
      await submitReview(sessionId, selectedAction, reviewerName, note, null);
      setToast('Review saved');
      setTimeout(() => { setToast(null); onBack(); }, 2500);
    } catch (err) {
      setToast(`Error: ${err.message}`);
      setSubmitting(false);
    }
  }, [submitting, selectedAction, sessionId, reviewerName, note, onBack]);

  // ── Manual flag submit ────────────────────────────────────────────────────
  const handleManualFlag = async (turn, turnIdx) => {
    if (flaggingProgress) return;
    setFlaggingProgress(true);
    try {
      await manualFlag(sessionId, {
        turn_id:       null,
        category_code: popoverCategory,
        note:          popoverNote,
        reviewer_id:   reviewerName,
        message_text:  (turn.message_text || '').slice(0, 200),
      });
      const updated = await getSessionFlags(sessionId);
      setFlags(updated);
      setOpenFlagPopover(null);
      setPopoverNote('');
      setConfirmedTurns((prev) => new Set([...prev, turnIdx]));
      setTimeout(() => {
        setConfirmedTurns((prev) => { const n = new Set(prev); n.delete(turnIdx); return n; });
      }, 2000);
    } catch (_) {
    } finally {
      setFlaggingProgress(false);
    }
  };

  // ── Session note auto-save (debounced 1.5 s) ──────────────────────────────
  const handleNoteChange = (value) => {
    setSessionNote(value);
    if (noteDebounceRef.current) clearTimeout(noteDebounceRef.current);
    noteDebounceRef.current = setTimeout(async () => {
      try {
        await saveSessionNote(sessionId, value, reviewerName);
        setNoteSaved(true);
        setTimeout(() => setNoteSaved(false), 2000);
      } catch (_) {}
    }, 1500);
  };

  // ── Error state ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 12, background: C.bgPage }}>
        <div style={{ fontSize: 14, color: C.severeText }}>Failed to load session.</div>
        <div style={{ fontSize: 12, color: C.textSecondary }}>{error}</div>
        <button onClick={onBack} className="btn-link-accent"
          style={{ fontSize: 13, color: C.accent, background: 'none', border: 'none', cursor: 'pointer' }}>
          ← Back to Queue
        </button>
      </div>
    );
  }

  const { session = {}, turns = [] } = data || {};
  const flagsByTurnIdx  = data ? buildFlagsByTurnIdx(turns, flags) : {};
  const firstFlaggedIdx = turns.findIndex((_, i) => flagsByTurnIdx[i]?.length > 0);
  const isReviewed      = session?.review_status && session.review_status !== 'PENDING' && session.reviewer_id;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: C.bgPage }}>

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 20px', background: C.bgSurface, borderBottom: `1px solid ${C.border}`,
        gap: 16, minHeight: 52,
      }}>
        <button onClick={onBack} className="btn-back-link"
          style={{ fontSize: 13, color: C.accent, background: 'none', border: 'none',
            cursor: 'pointer', flexShrink: 0, padding: 0 }}>
          ← Queue
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1,
          justifyContent: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13, fontFamily: MONO, color: C.textSecondary }}>{sessionId}</span>
          {!loading && <VerdictBadge verdict={session.overall_verdict} />}
          {!loading && session.language_detected && (
            <span style={{ fontSize: 11, fontFamily: MONO, background: C.bgStatsrow,
              border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 3, color: C.textSecondary }}>
              {session.language_detected}
            </span>
          )}
          {!loading && session.duration_minutes != null && (
            <span style={{ fontSize: 12, color: C.textMuted }}>
              {Math.round(session.duration_minutes)} min
            </span>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          {[{ label: '← Prev', id: prevId }, { label: 'Next →', id: nextId }].map(({ label, id }) => (
            <button key={label} disabled={!id} onClick={() => id && onNavigate(id)}
              className={id ? 'btn-nav' : ''}
              style={{
                padding: '5px 12px', fontSize: 12, border: `1px solid ${C.border}`,
                borderRadius: 4, background: C.bgSurface, color: id ? C.textPrimary : C.border,
                cursor: id ? 'pointer' : 'not-allowed', opacity: id ? 1 : 0.4, transition: 'background 150ms',
              }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* ── LEFT: Transcript ──────────────────────────────────────────── */}
        <div style={{ width: '60%', overflowY: 'auto', padding: 20, borderRight: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 10, fontFamily: MONO, textTransform: 'uppercase',
            letterSpacing: '0.08em', color: C.textMuted, marginBottom: 16 }}>
            Transcript
          </div>

          {loading ? <SkeletonPane /> : turns.length === 0 ? (
            <div style={{ fontSize: 13, color: C.textSecondary, fontStyle: 'italic' }}>
              No transcript available for this session.
            </div>
          ) : (
            turns.map((turn, idx) => {
              const isAstrologer   = turn.speaker === 'ASTROLOGER';
              const turnFlags      = flagsByTurnIdx[idx] || [];
              const isFirstFlagged = idx === firstFlaggedIdx;
              const isHovered      = hoveredTurnIdx === idx;
              const isPopoverOpen  = openFlagPopover === idx;

              const maxSev = turnFlags.length
                ? (turnFlags.some((f) => f.severity === 'HIGH') ? 'HIGH'
                  : turnFlags.some((f) => f.severity === 'MEDIUM') ? 'MEDIUM' : 'LOW')
                : null;
              const flagColor     = maxSev === 'HIGH' ? C.severeBorder : maxSev === 'MEDIUM' ? C.flaggedBorder : maxSev === 'LOW' ? C.cleanBorder : null;
              const flagBg        = maxSev === 'HIGH' ? C.severeBg    : maxSev === 'MEDIUM' ? C.flaggedBg    : maxSev === 'LOW' ? C.cleanBg    : null;
              const flagTextColor = maxSev === 'HIGH' ? C.severeText  : maxSev === 'MEDIUM' ? C.flaggedText  : maxSev === 'LOW' ? C.cleanText  : null;

              return (
                <div
                  key={turn.turn_id ?? idx}
                  ref={isFirstFlagged ? firstFlaggedRef : null}
                  style={{ display: 'flex', flexDirection: 'column',
                    alignItems: isAstrologer ? 'flex-start' : 'flex-end',
                    marginBottom: isPopoverOpen ? 0 : 16, position: 'relative' }}
                  onMouseEnter={() => setHoveredTurnIdx(idx)}
                  onMouseLeave={() => { if (!isPopoverOpen) setHoveredTurnIdx(null); }}
                >
                  {/* Category badges above bubble */}
                  {turnFlags.length > 0 && (
                    <div style={{ display: 'flex', gap: 4, marginBottom: 4, flexWrap: 'wrap' }}>
                      {turnFlags.map((f, fi) => (
                        <span key={fi} style={{
                          fontSize: 10, fontFamily: MONO, fontWeight: 500,
                          padding: '1px 6px', borderRadius: 3, textTransform: 'uppercase',
                          background: flagBg, color: flagTextColor, border: `1px solid ${flagColor}`,
                        }}>
                          {f.category_code}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Speaker label */}
                  <div style={{ fontSize: 10, fontFamily: MONO, textTransform: 'uppercase',
                    color: C.textSecondary, marginBottom: 4,
                    textAlign: isAstrologer ? 'left' : 'right' }}>
                    {isAstrologer ? 'Astrologer' : 'User'}
                  </div>

                  {/* Bubble + Flag button (flex row) */}
                  <div style={{
                    display: 'flex', alignItems: 'flex-start', gap: 6, maxWidth: '78%',
                    flexDirection: isAstrologer ? 'row' : 'row-reverse',
                  }}>
                    <div style={{
                      padding: '10px 14px',
                      borderRadius: isAstrologer ? '0 8px 8px 8px' : '8px 0 8px 8px',
                      fontSize: 13, lineHeight: 1.6,
                      background: isAstrologer ? '#F1F5F9' : '#EFF6FF',
                      color: C.textPrimary,
                      borderLeft: turnFlags.length > 0 ? `3px solid ${flagColor}` : undefined,
                      wordBreak: 'break-word', flex: 1,
                    }}>
                      {turn.message_text || '(empty)'}
                    </div>

                    {/* + Flag button — shows on hover */}
                    {(isHovered || isPopoverOpen) && (
                      <button
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isPopoverOpen) {
                            setOpenFlagPopover(null);
                          } else {
                            setOpenFlagPopover(idx);
                            setPopoverCategory(INTENT_CATEGORIES[0]);
                            setPopoverNote('');
                          }
                        }}
                        style={{
                          flexShrink: 0, alignSelf: 'flex-start',
                          fontSize: 11, fontFamily: MONO,
                          background: C.bgSurface,
                          border: `1px solid ${isPopoverOpen ? C.accent : C.border}`,
                          borderRadius: 3, padding: '2px 7px',
                          color: isPopoverOpen ? C.accent : C.textSecondary,
                          cursor: 'pointer', marginTop: 4,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        + Flag
                      </button>
                    )}
                  </div>

                  {/* "Flagged ✓" inline confirmation */}
                  {confirmedTurns.has(idx) && (
                    <div style={{ fontSize: 11, fontFamily: MONO, color: C.cleanText, marginTop: 3 }}>
                      ✓ Flagged
                    </div>
                  )}

                  {/* Timestamp */}
                  {turn.timestamp && (
                    <div style={{ fontSize: 10, fontFamily: MONO, color: C.textMuted, marginTop: 3,
                      textAlign: isAstrologer ? 'left' : 'right' }}>
                      {String(turn.timestamp).slice(11, 16)}
                    </div>
                  )}

                  {/* Inline popover — appears below the turn in document flow */}
                  {isPopoverOpen && (
                    <div
                      ref={popoverRef}
                      style={{
                        alignSelf: isAstrologer ? 'flex-start' : 'flex-end',
                        marginTop: 6, marginBottom: 16,
                        background: C.bgSurface,
                        border: `1px solid ${C.border}`,
                        borderRadius: 6, padding: 14, width: 280,
                        boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                        zIndex: 100,
                      }}
                    >
                      <div style={{ fontSize: 11, fontFamily: MONO, textTransform: 'uppercase',
                        letterSpacing: '0.06em', color: C.textSecondary, marginBottom: 8 }}>
                        Flag this message
                      </div>

                      <select
                        value={popoverCategory}
                        onChange={(e) => setPopoverCategory(e.target.value)}
                        style={{
                          width: '100%', border: `1px solid ${C.border}`, borderRadius: 4,
                          padding: '7px 10px', fontSize: 12, background: C.bgMuted, color: C.textPrimary,
                        }}
                      >
                        {INTENT_CATEGORIES.map((cat) => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>

                      <textarea
                        rows={2}
                        value={popoverNote}
                        onChange={(e) => setPopoverNote(e.target.value)}
                        onFocus={() => setPopoverNoteFocused(true)}
                        onBlur={() => setPopoverNoteFocused(false)}
                        placeholder="Why are you flagging this?"
                        style={{
                          width: '100%', marginTop: 8, border: `1px solid ${popoverNoteFocused ? C.accent : C.border}`,
                          borderRadius: 4, padding: '7px 10px', fontSize: 12,
                          background: popoverNoteFocused ? C.bgSurface : C.bgMuted,
                          resize: 'none', color: C.textPrimary,
                          transition: 'border-color 150ms, background 150ms',
                        }}
                      />

                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <button
                          onClick={() => setOpenFlagPopover(null)}
                          style={{
                            flex: 1, padding: '6px 0', fontSize: 12, background: C.bgSurface,
                            border: `1px solid ${C.border}`, borderRadius: 4, color: C.textSecondary, cursor: 'pointer',
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          disabled={flaggingProgress}
                          onClick={() => handleManualFlag(turn, idx)}
                          style={{
                            flex: 1, padding: '6px 0', fontSize: 12, fontWeight: 500,
                            background: flaggingProgress ? '#D4D0C9' : C.accent,
                            border: 'none', borderRadius: 4, color: '#FFFFFF', cursor: flaggingProgress ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {flaggingProgress ? '…' : 'Add Flag'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* ── RIGHT: Note + Flags + Review ──────────────────────────────── */}
        <div style={{ width: '40%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Feature 2 — Session Note (above flags) */}
          <div style={{
            flexShrink: 0, padding: '14px 20px 12px',
            borderBottom: `1px solid ${C.borderLight}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 10, fontFamily: MONO, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: C.textMuted }}>
                Session Note
              </span>
              {noteSaved && (
                <span style={{ fontSize: 10, fontFamily: MONO, color: C.accent }}>Saved</span>
              )}
            </div>
            <textarea
              rows={3}
              value={sessionNote}
              onChange={(e) => handleNoteChange(e.target.value)}
              onFocus={() => setSessionNoteFocused(true)}
              onBlur={() => setSessionNoteFocused(false)}
              placeholder="Add an overall observation about this session..."
              style={{
                width: '100%', padding: '10px 12px', fontSize: 13,
                border: `1px solid ${sessionNoteFocused ? C.accent : C.border}`,
                borderRadius: 5,
                background: sessionNoteFocused ? C.bgSurface : C.bgMuted,
                resize: 'none', color: C.textPrimary,
                transition: 'border-color 150ms, background 150ms',
              }}
            />
          </div>

          {/* Flags list */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
            <div style={{ fontSize: 10, fontFamily: MONO, textTransform: 'uppercase',
              letterSpacing: '0.08em', color: C.textMuted, marginBottom: 14 }}>
              Flags Detected
            </div>

            {loading ? <SkeletonPane /> : flags.length === 0 ? (
              <div style={{ fontSize: 13, color: C.textSecondary, fontStyle: 'italic' }}>
                No flags detected for this session.
              </div>
            ) : (
              flags.map((flag, fi) => {
                const ls = layerStyle(flag.detection_layer);
                return (
                  <div key={fi} style={{
                    background: C.bgSurface, border: `1px solid ${C.border}`,
                    borderRadius: 6, padding: '14px 16px', marginBottom: 10,
                  }}>
                    {/* Category + layer badge */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ fontSize: 13, fontFamily: MONO, fontWeight: 500,
                        color: C.textPrimary, textTransform: 'uppercase' }}>
                        {flag.category_code}
                      </span>
                      <span style={{
                        fontSize: 10, fontFamily: MONO, fontWeight: 500,
                        padding: '2px 7px', borderRadius: 3,
                        background: ls.bg, color: ls.text, border: `1px solid ${ls.border}`,
                      }}>
                        {flag.detection_layer}
                      </span>
                    </div>

                    {/* Severity + confidence + FP risk */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                      <VerdictBadge verdict={flag.severity} />
                      {flag.confidence_score != null && (
                        <span style={{ fontSize: 11, fontFamily: MONO, background: C.bgStatsrow,
                          border: `1px solid ${C.border}`, borderRadius: 3, padding: '2px 7px', color: C.textSecondary }}>
                          {Math.round(flag.confidence_score * 100)}%
                        </span>
                      )}
                      {flag.false_positive_risk && (
                        <span style={{ fontSize: 11, color: C.textSecondary }}>
                          FP risk: <b>{flag.false_positive_risk}</b>
                        </span>
                      )}
                    </div>

                    {/* Reasoning */}
                    {flag.reasoning && (
                      <div style={{ fontSize: 12, color: C.textSecondary, lineHeight: 1.5,
                        marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.borderLight}`, fontStyle: 'italic' }}>
                        {flag.reasoning}
                      </div>
                    )}

                    {/* "Flagged by" — only for MANUAL flags */}
                    {flag.flagged_by && (
                      <div style={{ fontSize: 11, fontFamily: MONO, color: C.textMuted, marginTop: 6 }}>
                        Flagged by {flag.flagged_by}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* ── Review panel ─────────────────────────────────────────────── */}
          <div style={{ flexShrink: 0, borderTop: `2px solid ${C.border}`, background: C.bgSurface, padding: 20 }}>
            {isReviewed && !showUpdateForm ? (
              <div>
                <div style={{ fontSize: 12, color: C.textSecondary, marginBottom: 6 }}>
                  Reviewed by <b>{session.reviewer_id}</b>
                  {' · '}{STATUS_LABEL[session.review_status] || session.review_status}
                </div>
                {session.reviewer_note && (
                  <div style={{ fontSize: 12, color: C.textSecondary, fontStyle: 'italic', marginBottom: 8 }}>
                    "{session.reviewer_note}"
                  </div>
                )}
                <button className="btn-link-accent" onClick={() => setShowUpdateForm(true)}
                  style={{ fontSize: 12, color: C.accent, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  Update decision
                </button>
              </div>
            ) : (
              <>
                <div style={{ fontSize: 10, fontFamily: MONO, textTransform: 'uppercase',
                  letterSpacing: '0.06em', color: C.textMuted, marginBottom: 12 }}>
                  Your Decision
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
                  {ACTIONS.map((a) => {
                    const isSelected = selectedAction === a.key;
                    const s = isSelected ? a.active : { bg: C.bgStatsrow, color: C.textSecondary, border: C.border };
                    return (
                      <button key={a.key} onClick={() => setSelectedAction(a.key)} style={{
                        padding: '9px 0', fontSize: 13, fontWeight: isSelected ? 600 : 500,
                        borderRadius: 5, border: `1px solid ${s.border}`, background: s.bg, color: s.color,
                        cursor: 'pointer', outline: isSelected ? `2px solid ${s.border}` : 'none',
                        outlineOffset: 1, transition: 'all 120ms',
                      }}>
                        {a.label}
                      </button>
                    );
                  })}
                </div>

                <textarea rows={3} placeholder="Add a note (optional)..." value={note}
                  onChange={(e) => setNote(e.target.value)}
                  onFocus={() => setNoteFocused(true)} onBlur={() => setNoteFocused(false)}
                  style={{
                    width: '100%', padding: '10px 12px', fontSize: 13,
                    border: `1px solid ${noteFocused ? C.accent : C.border}`,
                    borderRadius: 5, background: noteFocused ? C.bgSurface : C.bgMuted,
                    color: C.textPrimary, resize: 'vertical',
                    transition: 'border-color 150ms, background 150ms', marginBottom: 0,
                  }}
                />

                <button onClick={handleSubmit} disabled={!selectedAction || submitting} style={{
                  marginTop: 10, width: '100%', padding: 11, fontSize: 14, fontWeight: 500,
                  borderRadius: 5, border: 'none',
                  background: (!selectedAction || submitting) ? '#D4D0C9' : C.accent,
                  color: (!selectedAction || submitting) ? C.textMuted : '#FFFFFF',
                  cursor: (!selectedAction || submitting) ? 'not-allowed' : 'pointer',
                  animation: submitting ? 'pulse 1s ease-in-out infinite' : 'none',
                  transition: 'background 150ms',
                }}>
                  {submitting ? 'Saving…' : 'Submit Review'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {toast && <Toast message={toast} />}
    </div>
  );
}
