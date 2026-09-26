import { cn } from "@/lib/utils/cn";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  
  size?: "default" | "compact";
  
  
}

const CARD_PADDING = {
  default: "p-6",
  compact: "p-4",
} as const;


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
