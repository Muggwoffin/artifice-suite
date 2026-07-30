// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from 'react';
/** @startingPoint section="Core" subtitle="Removable mono-styled tag" viewport="700x100" */
export interface TagProps {
  children?: ReactNode;
  onRemove?: () => void;
}
