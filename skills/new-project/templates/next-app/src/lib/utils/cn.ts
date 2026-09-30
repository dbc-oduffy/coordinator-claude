import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Compose class strings with clsx and resolve Tailwind precedence conflicts (e.g. p-4 vs p-6) with tailwind-merge. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
