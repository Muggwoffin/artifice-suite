// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function Textarea({label,placeholder,rows=4,value,onChange}){
  return React.createElement('label',{style:{display:'flex',flexDirection:'column',gap:4,fontFamily:'var(--font-body)'}},
    label&&React.createElement('span',{style:{fontSize:12,fontWeight:500,color:'var(--text-secondary)'}},label),
    React.createElement('textarea',{rows,placeholder,value,onChange,style:{fontFamily:'var(--font-mono)',fontSize:13,lineHeight:1.6,color:'var(--text-primary)',background:'var(--surface-card-raised)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-sm)',padding:'8px 10px',outline:'none',resize:'vertical'}})
  );
}
