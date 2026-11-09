import React, { useEffect, useState } from "react";
import { Button } from "./Button";
import { useTranslation } from "../../lib/i18n";

export const ThemeToggle: React.FC = () => {
  const { t } = useTranslation();
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const saved = localStorage.getItem("shg_theme") as "light" | "dark" | null;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initial = saved || (prefersDark ? "dark" : "light");
    setTheme(initial);
    applyTheme(initial);
  }, []);

  const applyTheme = (targetTheme: "light" | "dark") => {
    if (targetTheme === "dark") {
      document.documentElement.classList.add("dark");
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.setAttribute("data-theme", "light");
    }
    localStorage.setItem("shg_theme", targetTheme);
  };

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    applyTheme(nextTheme);
  };

  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={toggleTheme}
      aria-label={theme === "light" ? t("theme.switchToDark") : t("theme.switchToLight")}
      className="flex items-center gap-1.5"
    >
      <span className="text-xs font-medium">
        {theme === "light" ? t("theme.dark") : t("theme.light")}
      </span>
      <span className="text-[10px] text-ink-muted uppercase tracking-wider">
        ({theme})
      </span>
    </Button>
  );
};
