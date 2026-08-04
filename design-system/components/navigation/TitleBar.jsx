// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function TitleBar({product,doc,actions}){
  return React.createElement('div',{style:{height:44,display:'flex',alignItems:'center',padding:'0 12px',background:'var(--surface-card)',borderBottom:'1px solid var(--border-subtle)',fontFamily:'var(--font-body)',gap:10}},
    React.createElement('span',{style:{font:'600 14px var(--font-display)',color:'var(--text-primary)'}},product),
    doc&&React.createElement('span',{style:{color:'var(--text-tertiary)',fontSize:13}},'/'),
    doc&&React.createElement('span',{style:{color:'var(--text-secondary)',fontSize:13,fontFamily:'var(--font-mono)'}},doc),
    React.createElement('div',{style:{flex:1}}),
    actions
  );
}
