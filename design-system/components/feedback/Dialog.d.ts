// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

import type { ReactNode } from 'react';
/** @startingPoint section="Feedback" subtitle="Modal confirmation dialog" viewport="700x260" */
export interface DialogProps {
  title: string;
  children?: ReactNode;
  onClose?: () => void;
  actions?: ReactNode;
}
