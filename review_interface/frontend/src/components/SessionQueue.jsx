import React, { useState, useEffect, useCallback } from 'react';
import { C, MONO } from '../tokens';
import TopBar from './TopBar';
import Footer from './Footer';
import VerdictBadge from './VerdictBadge';
import StatusBadge from './StatusBadge';
import LoadingSpinner from './LoadingSpinner';
import { getSessions, getStats, submitReview, getReviewerStats, exportCsv, getViolationStats } from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(str, n) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}

// Session type pill — Chat (blue) / Voice (purple)
function SessionTypePill({ stype }) {
  if (!stype) return <span style={{ color: C.textMuted }}>—</span>;
  const isVoice = stype === 'voice';
  return (
    <span style={{
      fontSize: 10, fontFamily: MONO, padding: '2px 8px', borderRadius: 3,
      background: isVoice ? C.voiceBg   : C.chatBg,
      color:      isVoice ? C.voiceText  : C.chatText,
      border:     `1px solid ${isVoice ? C.voiceBorder : C.chatBorder}`,
      textTransform: 'capitalize',
    }}>
      {stype}
    </span>
  );
}

// Feature 7 — Reviewer progress table columns
const PROGRESS_COLS = ['Reviewer', 'Reviewed', 'Confirmed', 'False Pos.', 'Escalated', 'Cleared'];

// Session table columns (Feature 3: Astrologer removed, Session Type added)
const COLS = ['Session ID', 'Verdict', 'Flags', 'Language', 'Type', 'Duration', 'Status', 'Action'];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SessionQueue({ reviewerName, onSelectSession }) {
  // ── Server-side filtered state ─────────────────────────────────────────
  const [sessions,      setSessions]      = useState([]);
  const [stats,         setStats]         = useState(null);
  const [loading,       setLoading]       = useState(true);
  const [verdictFilter, setVerdictFilter] = useState('');
  const [statusFilter,  setStatusFilter]  = useState('');
  const [hoveredRow,    setHoveredRow]    = useState(null);

  // ── Client-side filter state ───────────────────────────────────────────
  const [searchQuery,   setSearchQuery]   = useState('');       // Feature 6
  const [searchFocused, setSearchFocused] = useState(false);
  const [minConfidence, setMinConfidence] = useState(0);        // Feature 8

  // ── Action state ───────────────────────────────────────────────────────
  const [clearingSession, setClearingSession] = useState(null); // Feature 4
  const [exporting,       setExporting]       = useState(false);// Feature 5

  // ── Team progress state ────────────────────────────────────────────────
  const [showProgress,    setShowProgress]    = useState(false);// Feature 7
  const [reviewerStats,   setReviewerStats]   = useState([]);
  const [loadingProgress, setLoadingProgress] = useState(false);

  // ── Violation heatmap state ────────────────────────────────────────────
  const [showHeatmap,     setShowHeatmap]     = useState(false);
  const [heatmapData,     setHeatmapData]     = useState([]);
  const [loadingHeatmap,  setLoadingHeatmap]  = useState(false);

  // ── Data fetching ──────────────────────────────────────────────────────

  const fetchAll = useCallback(() => {
    return Promise.all([
      getSessions({ verdict: verdictFilter || undefined, status: statusFilter || undefined }),
      getStats(),
    ]).then(([sess, st]) => {
      setSessions(sess);
      setStats(st);
    }).catch(() => {});
  }, [verdictFilter, statusFilter]);

  useEffect(() => {
    setLoading(true);
    fetchAll().finally(() => setLoading(false));
  }, [fetchAll]);

  useEffect(() => {
    const id = setInterval(fetchAll, 30_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  // ── Derived values ─────────────────────────────────────────────────────

  const clearFilters = () => { setVerdictFilter(''); setStatusFilter(''); };
  const hasFilters   = verdictFilter || statusFilter;

  const severe   = stats?.count_severe   ?? 0;
  const flagged  = stats?.count_flagged  ?? 0;
  const clean    = stats?.count_clean    ?? 0;
  const total    = stats?.total_sessions ?? 0;
  const pending  = stats?.total_pending  ?? 0;
  const reviewed = total - pending;

  const statCells = [
    { label: 'Severe',         value: severe,   color: C.severeText  },
    { label: 'Flagged',        value: flagged,  color: C.flaggedText },
    { label: 'Clean',          value: clean,    color: C.cleanText   },
    { label: 'Total sessions', value: total,    color: C.textPrimary },
    { label: 'Pending review', value: pending,  color: C.accent      },
  ];

  // Client-side filters applied on top of server-filtered list
  const displayedSessions = sessions
    .filter((s) => !searchQuery.trim() || s.session_id.includes(searchQuery.trim()))
    .filter((s) => minConfidence === 0 || ((s.confidence_score ?? 0) * 100 >= minConfidence));

  const noResults     = displayedSessions.length === 0;
  const emptyMessage  = sessions.length === 0
    ? 'No sessions match the selected filters.'
    : 'No sessions match the search or confidence filter.';
  const showClearLink = sessions.length === 0 && hasFilters;
  const heatmapMax    = heatmapData.length > 0 ? Math.max(...heatmapData.map(d => d.count)) : 1;

  // ── Feature 4 — Quick-clear ────────────────────────────────────────────

  const handleQuickClear = async (sid) => {
    if (clearingSession) return;
    setClearingSession(sid);
    try {
      await submitReview(sid, 'CLEAR', reviewerName, 'Cleared from queue without full review', null);
      await fetchAll();
    } catch (_) {
    } finally {
      setClearingSession(null);
    }
  };

  // ── Feature 5 — Export CSV ─────────────────────────────────────────────

  const handleExport = () => {
    setExporting(true);
    exportCsv();
    setTimeout(() => setExporting(false), 1000);
  };

  // ── Violation heatmap ──────────────────────────────────────────────────

  const CATEGORY_COLORS = {
    OFF_PLATFORM_SOLICITATION:   '#0F6E56',
    NSFW:                        '#A32D2D',
    FEAR_MANIPULATION:           '#854F0B',
    FINANCIAL_SOLICITATION:      '#854F0B',
    PERSONAL_DATA_COLLECTION:    '#185FA5',
    ABUSIVE_LANGUAGE:            '#A32D2D',
    HATE_SPEECH:                 '#A32D2D',
    IDENTITY_FRAUD:              '#185FA5',
    FAKE_REMEDIES:               '#854F0B',
    UNAUTHORIZED_MEDICAL_ADVICE: '#3B6D11',
    COMPETITOR_PROMOTION:        '#6B6860',
    OTHER:                       '#6B6860',
  };

  const handleToggleHeatmap = () => {
    const next = !showHeatmap;
    setShowHeatmap(next);
    if (next) {
      setLoadingHeatmap(true);
      getViolationStats()
        .then((data) => { setHeatmapData(data); setLoadingHeatmap(false); })
        .catch(() => setLoadingHeatmap(false));
    }
  };

  // ── Feature 7 — Team Progress toggle ──────────────────────────────────

  const handleToggleProgress = () => {
    const next = !showProgress;
    setShowProgress(next);
    if (next && reviewerStats.length === 0) {
      setLoadingProgress(true);
      getReviewerStats()
        .then((data) => { setReviewerStats(data); setLoadingProgress(false); })
        .catch(() => setLoadingProgress(false));
    }
  };

  // ── Shared styles ──────────────────────────────────────────────────────

  const selectSt = {
    padding: '6px 10px', fontSize: 13, fontFamily: 'inherit',
    border: `1px solid ${C.border}`, borderRadius: 4,
    background: C.bgSurface, color: C.textPrimary, cursor: 'pointer',
  };

  const th = {
    padding: '9px 14px', textAlign: 'left', fontSize: 10, fontFamily: MONO, fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.06em', color: C.textSecondary,
    background: C.bgStatsrow, borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap',
  };

  const td = (last) => ({
    padding: '10px 14px', fontSize: 13,
    borderBottom: last ? 'none' : `1px solid ${C.borderLight}`,
    color: C.textPrimary, verticalAlign: 'middle',
  });

  const tdMono = (last) => ({ ...td(last), fontFamily: MONO, fontSize: 12, color: C.textSecondary });

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <TopBar reviewerName={reviewerName} />

      {/* Sub-bar: filters + right controls */}
      <div style={{
        flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 20px', background: C.bgSurface, borderBottom: `1px solid ${C.border}`,
        gap: 12, flexWrap: 'wrap',
      }}>

        {/* Left group: search + filter selects + confidence + clear */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {/* Feature 6 — Search */}
          <input
            type="text"
            placeholder="Search session ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            style={{
              width: 180, padding: '6px 12px', fontSize: 12,
              border: `1px solid ${searchFocused ? C.accent : C.border}`,
              borderRadius: 4, background: searchFocused ? C.bgSurface : C.bgMuted,
              color: C.textPrimary, transition: 'border-color 150ms, background 150ms',
            }}
          />

          <span style={{ fontSize: 11, fontFamily: MONO, textTransform: 'uppercase', color: C.textSecondary }}>
            Filter:
          </span>

          <select style={selectSt} value={verdictFilter} onChange={(e) => setVerdictFilter(e.target.value)}>
            <option value="">All Verdicts</option>
            <option value="SEVERE">SEVERE</option>
            <option value="FLAGGED">FLAGGED</option>
            <option value="CLEAN">CLEAN</option>
          </select>

          <select style={selectSt} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Statuses</option>
            <option value="PENDING">PENDING</option>
            <option value="REVIEWED">REVIEWED</option>
            <option value="CONFIRMED">CONFIRMED</option>
            <option value="OVERRIDDEN">OVERRIDDEN</option>
            <option value="ESCALATED">ESCALATED</option>
          </select>

          {/* Feature 8 — Confidence slider */}
          <span style={{ fontSize: 11, fontFamily: MONO, color: C.textSecondary, whiteSpace: 'nowrap' }}>
            Min confidence:
          </span>
          <input
            type="range" min={0} max={100} step={5} value={minConfidence}
            onChange={(e) => setMinConfidence(Number(e.target.value))}
            style={{ width: 100, accentColor: C.accent, cursor: 'pointer' }}
          />
          <span style={{ fontSize: 11, fontFamily: MONO, color: C.accent, minWidth: 28 }}>
            {minConfidence}%
          </span>

          {hasFilters && (
            <button className="btn-link-accent" onClick={clearFilters}
              style={{ fontSize: 12, color: C.accent, background: 'none', border: 'none',
                cursor: 'pointer', marginLeft: 4, padding: 0 }}>
              Clear filters
            </button>
          )}
        </div>

        {/* Right group: Team Progress toggle + Export + progress pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <button
            onClick={handleToggleProgress}
            style={{
              fontSize: 12, padding: '5px 12px', background: C.bgSurface,
              border: `1px solid ${C.border}`, borderRadius: 4,
              color: showProgress ? C.accent : C.textPrimary, cursor: 'pointer',
            }}
          >
            Team Progress {showProgress ? '▴' : '▾'}
          </button>

          <button
            onClick={handleExport}
            style={{
              fontSize: 12, padding: '5px 14px', background: C.bgSurface,
              border: `1px solid ${C.border}`, borderRadius: 4,
              color: C.textPrimary, cursor: 'pointer',
            }}
          >
            {exporting ? 'Exporting…' : '↓ Export CSV'}
          </button>

          <div style={{
            fontSize: 11, fontFamily: MONO, background: C.bgStatsrow,
            border: `1px solid ${C.border}`, borderRadius: 4, padding: '4px 12px',
            color: C.textSecondary, whiteSpace: 'nowrap',
          }}>
            <span style={{ color: C.accent, fontWeight: 500 }}>{reviewed}</span>
            {' of '}
            <span style={{ color: C.textPrimary }}>{total}</span>
            {' reviewed'}
          </div>
        </div>
      </div>

      {/* Stats strip */}
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'stretch', background: C.bgStatsrow, borderBottom: `1px solid ${C.border}` }}>
        {statCells.map((cell) => (
          <div key={cell.label} style={{ flex: 1, padding: '10px 20px',
            borderRight: `1px solid ${C.border}` }}>
            <div style={{ fontSize: 18, fontFamily: MONO, fontWeight: 500, color: cell.color }}>
              {cell.value}
            </div>
            <div style={{ fontSize: 11, color: C.textSecondary, marginTop: 2 }}>{cell.label}</div>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', padding: '0 20px', flexShrink: 0 }}>
          <span
            onClick={handleToggleHeatmap}
            style={{ fontSize: 11, fontFamily: MONO, color: '#0F6E56', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Violation Breakdown {showHeatmap ? '▴' : '▾'}
          </span>
        </div>
      </div>

      {/* Violation heatmap — collapsible */}
      {showHeatmap && (
        <div style={{
          flexShrink: 0, margin: '0 20px 12px', background: '#FFFFFF',
          border: '1px solid #E2DED8', borderRadius: 6, padding: '16px 20px',
        }}>
          {loadingHeatmap ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10,
              color: C.textSecondary, fontSize: 13 }}>
              <LoadingSpinner size={16} /> Loading…
            </div>
          ) : heatmapData.length === 0 ? (
            <div style={{ fontSize: 13, color: '#6B6860', fontStyle: 'italic', textAlign: 'center' }}>
              No violation data yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {heatmapData.map((item) => (
                <div key={item.category_code} style={{ display: 'flex', alignItems: 'center', height: 32 }}>
                  <span style={{
                    fontSize: 13, fontFamily: MONO, color: '#1C1C1A',
                    width: 260, flexShrink: 0,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {item.category_code}
                  </span>
                  <div style={{
                    flex: 1, height: 8, background: '#E2DED8',
                    borderRadius: 4, margin: '0 12px', position: 'relative',
                  }}>
                    <div style={{
                      height: '100%', borderRadius: 4,
                      width: `${(item.count / heatmapMax) * 100}%`,
                      background: CATEGORY_COLORS[item.category_code] ?? '#6B6860',
                    }} />
                  </div>
                  <span style={{
                    fontSize: 13, fontFamily: MONO, color: '#6B6860',
                    minWidth: 32, textAlign: 'right',
                  }}>
                    {item.count}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Feature 7 — Team Progress collapsible section */}
      {showProgress && (
        <div style={{ flexShrink: 0, padding: '12px 20px', background: C.bgSurface,
          borderBottom: `1px solid ${C.border}` }}>
          {loadingProgress ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
              color: C.textSecondary, fontSize: 13 }}>
              <LoadingSpinner size={16} /> Loading reviewer stats…
            </div>
          ) : reviewerStats.length === 0 ? (
            <div style={{ fontSize: 13, color: C.textSecondary, padding: '6px 0' }}>
              No review activity yet.
            </div>
          ) : (
            <div style={{ border: `1px solid ${C.border}`, borderRadius: 6, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', background: C.bgSurface }}>
                <thead>
                  <tr style={{ background: C.bgStatsrow, borderBottom: `1px solid ${C.border}` }}>
                    {PROGRESS_COLS.map((h) => (
                      <th key={h} style={{
                        padding: '7px 14px', textAlign: 'left', fontSize: 10,
                        fontFamily: MONO, fontWeight: 600, textTransform: 'uppercase',
                        letterSpacing: '0.06em', color: C.textSecondary, whiteSpace: 'nowrap',
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reviewerStats.map((r, i) => {
                    const isLast = i === reviewerStats.length - 1;
                    const border = isLast ? 'none' : `1px solid ${C.borderLight}`;
                    const cellSt = { padding: '7px 14px', fontSize: 12, fontFamily: MONO,
                      color: C.textPrimary, borderBottom: border };
                    return (
                      <tr key={r.reviewer_id} style={{ background: C.bgSurface }}>
                        <td style={{ ...cellSt, color: C.textPrimary }}>{r.reviewer_id}</td>
                        <td style={{ ...cellSt, color: C.accent, fontWeight: 500 }}>{r.sessions_reviewed}</td>
                        <td style={cellSt}>{r.confirmed}</td>
                        <td style={cellSt}>{r.false_positives}</td>
                        <td style={{ ...cellSt, color: r.escalated > 0 ? C.severeText : C.textPrimary }}>
                          {r.escalated}
                        </td>
                        <td style={cellSt}>{r.cleared}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Table area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '60px 0', gap: 12, color: C.textSecondary, fontSize: 14 }}>
            <LoadingSpinner /> Loading sessions…
          </div>
        ) : noResults ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <div style={{ fontSize: 13, color: C.textSecondary }}>{emptyMessage}</div>
            {showClearLink && (
              <button className="btn-link-accent" onClick={clearFilters}
                style={{ display: 'block', margin: '10px auto 0', fontSize: 13,
                  color: C.accent, background: 'none', border: 'none', cursor: 'pointer' }}>
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <div style={{ border: `1px solid ${C.border}`, borderRadius: 6, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', background: C.bgSurface }}>
              <thead>
                <tr style={{ background: C.bgStatsrow, borderBottom: `1px solid ${C.border}` }}>
                  {COLS.map((h) => <th key={h} style={th}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {displayedSessions.map((s, idx) => {
                  const isLast    = idx === displayedSessions.length - 1;
                  const isHovered = hoveredRow === s.session_id;
                  const isClearing = clearingSession === s.session_id;
                  return (
                    <tr
                      key={s.session_id}
                      className="session-row"
                      onMouseEnter={() => setHoveredRow(s.session_id)}
                      onMouseLeave={() => setHoveredRow(null)}
                      style={{ background: isHovered ? C.bgMuted : C.bgSurface, transition: 'background 150ms' }}
                    >
                      <td style={tdMono(isLast)}>{s.session_id}</td>

                      <td style={td(isLast)}><VerdictBadge verdict={s.overall_verdict} /></td>

                      <td style={td(isLast)}>
                        {s.flag_count > 0 ? (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                            <span style={{
                              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                              background: s.overall_verdict === 'SEVERE' ? C.severeText
                                : s.overall_verdict === 'FLAGGED' ? C.flaggedText : C.cleanText,
                            }} />
                            <span style={{ fontFamily: MONO, fontSize: 12 }}>{s.flag_count}</span>
                          </span>
                        ) : (
                          <span style={{ color: C.textMuted }}>—</span>
                        )}
                      </td>

                      {/* Feature 3: Language */}
                      <td style={td(isLast)}>
                        <span style={{ textTransform: 'capitalize', fontSize: 13 }}>
                          {s.language_detected || '—'}
                        </span>
                      </td>

                      {/* Feature 3: Session Type (replaces Astrologer) */}
                      <td style={td(isLast)}>
                        <SessionTypePill stype={s.session_type} />
                      </td>

                      <td style={tdMono(isLast)}>
                        {s.duration_minutes != null ? `${Math.round(s.duration_minutes)} min` : '—'}
                      </td>

                      <td style={td(isLast)}><StatusBadge status={s.review_status} /></td>

                      {/* Feature 4: Action column with Clear + Review buttons */}
                      <td style={td(isLast)}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {/* Quick-clear — only for PENDING sessions */}
                          {s.review_status === 'PENDING' && (
                            <button
                              disabled={!!clearingSession}
                              onClick={() => handleQuickClear(s.session_id)}
                              style={{
                                padding: '5px 10px', fontSize: 11, background: C.bgSurface,
                                border: `1px solid ${isClearing ? C.accent : C.border}`,
                                borderRadius: 4, color: isClearing ? C.accent : C.textSecondary,
                                cursor: clearingSession ? 'not-allowed' : 'pointer',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {isClearing ? '…' : '✓ Clear'}
                            </button>
                          )}

                          <button
                            className="review-btn"
                            onClick={() => onSelectSession(s.session_id, sessions)}
                            style={{
                              padding: '5px 14px', fontSize: 12, fontWeight: 500,
                              background: C.accent, color: '#FFFFFF', border: 'none',
                              borderRadius: 4, transition: 'background 150ms', whiteSpace: 'nowrap',
                            }}
                          >
                            Review →
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Footer />
    </div>
  );
}
