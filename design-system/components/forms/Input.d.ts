// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

/** @startingPoint section="Forms" subtitle="Labeled text input" viewport="700x120" */
export interface InputProps {
  label?: string;
  placeholder?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
}
