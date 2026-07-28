import React from 'react';
export function Badge({tone='neutral',children}){
  const tones={
    neutral:{background:'var(--parchment-400)',color:'var(--ink-700)'},
    success:{background:'var(--sage-100)',color:'var(--sage-700)'},
    warning:{background:'var(--state-warning-soft)',color:'var(--state-warning)'},
    danger:{background:'var(--state-danger-soft)',color:'var(--state-danger)'}
  };
  return React.createElement('span',{style:{...tones[tone],fontFamily:'var(--font-body)',fontSize:11,fontWeight:600,letterSpacing:'var(--tracking-label)',textTransform:'uppercase',padding:'3px 8px',borderRadius:'var(--radius-pill)',display:'inline-block'}},children);
}
