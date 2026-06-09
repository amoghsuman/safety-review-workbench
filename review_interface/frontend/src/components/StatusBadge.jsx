import React from 'react';
import { C, MONO } from '../tokens';

const PENDING = { bg: C.bgStatsrow, border: '#D4D0C9', text: C.textSecondary };
const DONE    = { bg: C.accentLight, border: '#9FE1CB', text: C.accentDark };

export default function StatusBadge({ status }) {
  const s = status === 'PENDING' ? PENDING : DONE;
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 3,
      border: `1px solid ${s.border}`,
      fontSize: 10,
      fontFamily: MONO,
      fontWeight: 500,
      textTransform: 'uppercase',
      letterSpacing: '0.04em',
      background: s.bg,
      color: s.text,
      whiteSpace: 'nowrap',
    }}>
      {status}
    </span>
  );
}
