import {
  ComputerDesktopIcon,
  SunIcon,
  MoonIcon,
} from "@heroicons/react/20/solid";
import { useTheme, type ThemeMode } from "@/hooks/useTheme";

const CYCLE: ThemeMode[] = ["system", "light", "dark"];

const ICONS: Record<ThemeMode, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  system: ComputerDesktopIcon,
  light: SunIcon,
  dark: MoonIcon,
};

const NEXT_LABELS: Record<ThemeMode, string> = {
  system: "Switch to light theme",
  light: "Switch to dark theme",
  dark: "Switch to system theme",
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  const Icon = ICONS[theme];

  function handleClick() {
    const idx = CYCLE.indexOf(theme);
    const next = CYCLE[(idx + 1) % CYCLE.length];
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={NEXT_LABELS[theme]}
      className="rounded-md p-2 text-tf-text-secondary transition-colors hover:bg-tf-bg-elevated hover:text-tf-text-primary"
    >
      <Icon className="h-5 w-5" />
    </button>
  );
}
