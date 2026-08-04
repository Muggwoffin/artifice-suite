// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function Sidebar({items=[],activeId,onSelect,footer}){
  return React.createElement('div',{style:{width:220,background:'var(--parchment-200)',borderRight:'1px solid var(--border-subtle)',display:'flex',flexDirection:'column',height:'100%',fontFamily:'var(--font-body)'}},
    React.createElement('div',{style:{flex:1,overflowY:'auto',padding:8}},
      items.map(it=>React.createElement('div',{key:it.id,onClick:()=>onSelect&&onSelect(it.id),style:{padding:'7px 10px',borderRadius:'var(--radius-sm)',fontSize:13,color:it.id===activeId?'var(--text-primary)':'var(--text-secondary)',background:it.id===activeId?'var(--surface-card-raised)':'transparent',cursor:'pointer',display:'flex',justifyContent:'space-between',alignItems:'center'}},
        React.createElement('span',null,it.label),
        it.meta&&React.createElement('span',{style:{fontSize:11,color:'var(--text-tertiary)',fontFamily:'var(--font-mono)'}},it.meta)
      ))
    ),
    footer&&React.createElement('div',{style:{borderTop:'1px solid var(--border-subtle)',padding:10}},footer)
  );
}
