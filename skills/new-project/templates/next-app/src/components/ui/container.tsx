import { cn } from "@/lib/utils/cn";

interface ContainerProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Responsive container with max-width and padding.
 *
 * Padding: 24px (mobile) → 40px (md) → 56px (lg) → 10vw (2xl+)
 * Max-width: screen-2xl (1536px). 2xl padding is viewport-relative
 * because no Tailwind spacing token maps cleanly to a vw unit.
 */
export function Container({ children, className }: ContainerProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-screen-2xl px-6 md:px-10 lg:px-14 2xl:px-[10vw]",
        className
      )}
    >
      {children}
    </div>
  );
}
