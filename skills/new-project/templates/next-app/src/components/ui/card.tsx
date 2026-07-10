import { cn } from "@/lib/utils/cn";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  /** Padding size variant. Defaults to "default" (p-6). */
  size?: "default" | "compact";
  // Interactive variant not provided: a bare onClick div is not keyboard-accessible.
  // Add a dedicated interactive variant (button role + keyboard handler) before using click-triggered cards.
}

const CARD_PADDING = {
  default: "p-6",
  compact: "p-4",
} as const;

/**
 * Card container with background, border, and rounded corners.
 */
export function Card({ children, className, size = "default" }: CardProps) {
  return (
    <div
      className={cn(
        "bg-card rounded-xl border border-border",
        CARD_PADDING[size],
        className
      )}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export function CardHeader({ children, className }: CardHeaderProps) {
  return <div className={cn("mb-4", className)}>{children}</div>;
}

interface CardTitleProps {
  children: React.ReactNode;
  className?: string;
}

export function CardTitle({ children, className }: CardTitleProps) {
  return (
    <h3
      className={cn(
        "text-sm font-semibold uppercase tracking-wide text-muted-foreground",
        className
      )}
    >
      {children}
    </h3>
  );
}

interface CardContentProps {
  children: React.ReactNode;
  className?: string;
  id?: string;
}

export function CardContent({ children, className, id }: CardContentProps) {
  return (
    <div id={id} className={className}>
      {children}
    </div>
  );
}
