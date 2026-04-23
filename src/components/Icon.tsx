import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface IconProps {
  name: string;
  fill?: number;
  size?: number;
  className?: string;
}

export function Icon({ name, fill = 0, size = 24, className = "" }: IconProps) {
  return (
    <span
      className={cn("material-symbols-outlined select-none leading-none", className)}
      style={{ 
        fontSize: size, 
        fontVariationSettings: `'FILL' ${fill}, 'wght' 400, 'GRAD' 0, 'opsz' 24` 
      }}
    >
      {name}
    </span>
  );
}
