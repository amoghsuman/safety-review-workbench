import React from 'react';
import { C, MONO } from '../tokens';

export default function Footer() {
  return (
    <div style={{
      height: 40,
      flexShrink: 0,
      background: C.bgPage,
      borderTop: `1px solid ${C.border}`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 20px',
    }}>
      <span style={{ fontSize: 10, fontFamily: MONO, color: C.textMuted }}>
        Grant Thornton Bharat LLP · Confidential
      </span>
      <span style={{ fontSize: 10, fontFamily: MONO, color: C.textMuted }}>
        v1.0 · 2026
      </span>
    </div>
  );
}
