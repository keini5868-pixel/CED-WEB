export const CED_THEME_STORAGE_KEY = "ced-theme";

export type CedTheme = "petrol" | "light";

export function isCedTheme(value: string | null | undefined): value is CedTheme {
  return value === "petrol" || value === "light";
}

export function readStoredCedTheme(): CedTheme {
  if (typeof window === "undefined") return "petrol";
  try {
    const stored = window.localStorage.getItem(CED_THEME_STORAGE_KEY);
    if (isCedTheme(stored)) return stored;
  } catch {
    /* ignore */
  }
  const attr = document.documentElement.getAttribute("data-ced-theme");
  return isCedTheme(attr) ? attr : "petrol";
}

export function applyCedTheme(theme: CedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-ced-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", theme === "light" ? "#f4f9fd" : "#042830");
  }
  try {
    window.localStorage.setItem(CED_THEME_STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}
