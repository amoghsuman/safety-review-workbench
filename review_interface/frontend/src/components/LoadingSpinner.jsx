import React from 'react';
import { C } from '../tokens';

export default function LoadingSpinner({ size = 20, color = C.accent }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        border: `2px solid ${C.border}`,
        borderTopColor: color,
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
        display: 'inline-block',
        flexShrink: 0,
      }}
    />
  );
}
