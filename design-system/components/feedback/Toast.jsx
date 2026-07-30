// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

import React from 'react';
export function Toast({tone='neutral',children,onClose}){
  const tones={neutral:'var(--ink)',success:'var(--accent-darker)',danger:'var(--state-danger)'};
  return React.createElement('div',{style:{background:tones[tone],color:'var(--paper-raised)',fontFamily:'var(--font-label)',fontSize:13,padding:'10px 14px',borderRadius:'var(--radius-md)',boxShadow:'var(--shadow-md)',display:'flex',alignItems:'center',gap:12,maxWidth:320}},
    React.createElement('span',{style:{flex:1}},children),
    onClose&&React.createElement('button',{onClick:onClose,style:{background:'none',border:'none',color:'inherit',opacity:0.7,cursor:'pointer'}},'\u00d7')
  );
}
