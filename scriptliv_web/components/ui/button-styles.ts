import { cva, type VariantProps } from "class-variance-authority";

/* Pill button recipe. Plain module (no "use client") so server components can style links with it. */
export const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-all focus-visible:outline-none disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary: "brand-gradient shadow-[var(--glow)] hover:brightness-110",
        secondary: "bg-surface-alt text-ink hover:brightness-110 border border-line",
        ghost: "text-ink-2 hover:bg-surface-alt hover:text-ink",
        danger: "bg-error text-white dark:text-[#1a0610] hover:brightness-110",
        outline: "border border-violet/60 text-ink hover:bg-surface-alt",
      },
      size: { sm: "h-9 px-4 text-sm", md: "h-11 px-5 text-sm", lg: "h-12 px-7 text-base" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);
export type ButtonVariants = VariantProps<typeof button>;
export const buttonCls = (o?: ButtonVariants) => button(o);
