import Image from "next/image";

type LogoProps = { className?: string; alt?: string };

/**
 * Nex Edu logo. The dark variant swaps the navy cap and "Nex" for white so
 * they stay visible on dark surfaces; Tailwind's dark: follows the OS setting.
 * Images stay lazy so the browser skips whichever variant is hidden.
 */
export function Logo({ className = "h-10", alt = "Nex Edu" }: LogoProps) {
  return (
    <>
      <Image
        src="/brand/nex-edu-logo.png"
        alt={alt}
        width={772}
        height={365}
        className={`block w-auto dark:hidden ${className}`}
      />
      <Image
        src="/brand/nex-edu-logo-dark.png"
        alt={alt}
        width={772}
        height={365}
        className={`hidden w-auto dark:block ${className}`}
      />
    </>
  );
}

/** The cap-and-book "N" on its own, for tight spaces. */
export function LogoMark({ className = "h-8", alt = "Nex Edu" }: LogoProps) {
  return (
    <>
      <Image
        src="/brand/nex-edu-mark.png"
        alt={alt}
        width={349}
        height={365}
        className={`block w-auto dark:hidden ${className}`}
      />
      <Image
        src="/brand/nex-edu-mark-dark.png"
        alt={alt}
        width={349}
        height={365}
        className={`hidden w-auto dark:block ${className}`}
      />
    </>
  );
}
