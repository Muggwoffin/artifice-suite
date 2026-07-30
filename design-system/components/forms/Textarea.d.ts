// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

/** @startingPoint section="Forms" subtitle="Multi-line mono text area" viewport="700x160" */
export interface TextareaProps {
  label?: string;
  placeholder?: string;
  rows?: number;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
}
