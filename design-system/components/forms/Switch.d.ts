/** @startingPoint section="Forms" subtitle="Toggle switch" viewport="700x100" */
export interface SwitchProps {
  label?: string;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
}
