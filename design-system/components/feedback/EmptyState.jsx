// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
export function EmptyState({title,description,action}){
  return React.createElement('div',{style:{textAlign:'center',padding:'40px 20px',fontFamily:'var(--font-body)'}},
    React.createElement('div',{style:{font:'var(--text-headline)',color:'var(--text-primary)',marginBottom:6}},title),
    React.createElement('div',{style:{font:'var(--text-body)',color:'var(--text-tertiary)',marginBottom:16}},description),
    action
  );
}
