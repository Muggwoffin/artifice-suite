// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from 'react';
/** @startingPoint section="Surfaces" subtitle="Titled content panel" viewport="700x220" */
export interface PanelProps {
  title?: string;
  actions?: ReactNode;
  children?: ReactNode;
}
