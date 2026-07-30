// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

import React from 'react';
export function Card({title,meta,children}){
  const [hover,setHover]=React.useState(false);
  return React.createElement('div',{onMouseEnter:()=>setHover(true),onMouseLeave:()=>setHover(false),style:{background:'var(--surface-card)',border:`1px solid ${hover?'var(--rule-dark)':'var(--border-subtle)'}`,borderRadius:'var(--radius-lg)',padding:14,fontFamily:'var(--font-body)',boxShadow:hover?'var(--shadow-lifted)':'var(--shadow-paper)',transform:hover?'translateY(-4px)':'none',transition:'transform var(--duration-normal) var(--ease-primary),box-shadow var(--duration-normal) ease,border-color var(--duration-normal) ease'}},
    (title||meta)&&React.createElement('div',{style:{display:'flex',justifyContent:'space-between',marginBottom:8}},
      title&&React.createElement('span',{style:{font:'var(--text-title)',color:'var(--text-primary)'}},title),
      meta&&React.createElement('span',{style:{fontSize:12,color:'var(--text-tertiary)'}},meta)
    ),
    children
  );
}
