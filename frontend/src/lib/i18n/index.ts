import { en } from "./en";

type NestedRecord = { [key: string]: string | NestedRecord };

function getNestedValue(obj: NestedRecord, path: string): string | undefined {
  const parts = path.split(".");
  let current: any = obj;
  for (const part of parts) {
    if (current === undefined || current === null || typeof current !== "object") {
      return undefined;
    }
    current = current[part];
  }
  return typeof current === "string" ? current : undefined;
}

export function t(key: string, params?: Record<string, string | number>): string {
  const value = getNestedValue(en, key);
  if (!value) {
    return key;
  }
  if (!params) {
    return value;
  }
  return Object.entries(params).reduce((acc, [paramKey, paramVal]) => {
    return acc.replace(new RegExp(`{${paramKey}}`, "g"), String(paramVal));
  }, value);
}

export function useTranslation() {
  return { t, strings: en };
}
