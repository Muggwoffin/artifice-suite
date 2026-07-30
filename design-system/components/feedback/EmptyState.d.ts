// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from 'react';
/** @startingPoint section="Feedback" subtitle="Empty / zero-state panel" viewport="700x220" */
export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}
