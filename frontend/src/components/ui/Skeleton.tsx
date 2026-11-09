import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "rectangular" | "circular";
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  variant = "rectangular",
  width,
  height,
  className,
  style,
  ...props
}) => {
  const variantStyles = {
    text: "h-4 w-full rounded-sm",
    rectangular: "h-10 w-full rounded-sm",
    circular: "h-10 w-10 rounded-full",
  }[variant];

  return (
    <div
      className={twMerge(
        clsx(
          "bg-surface-sunken animate-pulse border border-border/50",
          variantStyles,
          className
        )
      )}
      style={{
        width: typeof width === "number" ? `${width}px` : width,
        height: typeof height === "number" ? `${height}px` : height,
        ...style,
      }}
      aria-hidden="true"
      {...props}
    />
  );
};
