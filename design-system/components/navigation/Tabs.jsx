// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function Tabs({items=[],active,onChange}){
  return React.createElement('div',{style:{display:'flex',gap:4,borderBottom:'1px solid var(--border-subtle)',fontFamily:'var(--font-body)'}},
    items.map(it=>React.createElement('button',{key:it,onClick:()=>onChange&&onChange(it),style:{background:'none',border:'none',borderBottom:it===active?'2px solid var(--sage-600)':'2px solid transparent',color:it===active?'var(--text-primary)':'var(--text-tertiary)',fontWeight:it===active?600:400,fontSize:13,padding:'8px 4px',marginBottom:-1,cursor:'pointer'}},it))
  );
}
