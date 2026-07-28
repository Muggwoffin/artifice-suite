/** @startingPoint section="Forms" subtitle="Native-style dropdown" viewport="700x120" */
export interface SelectProps {
  label?: string;
  options?: string[];
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
}
