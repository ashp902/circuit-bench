import type { ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "tertiary" | "danger";
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant };

export function Button({ className = "", variant = "secondary", ...props }: ButtonProps) {
  return <button {...props} className={`button button--${variant} ${className}`.trim()} />;
}
