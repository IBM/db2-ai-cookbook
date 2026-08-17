import { useTheme } from "../context/ThemeContext";

const ThemeSwitcher = () => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      style={{
        padding: "0.4rem 0.8rem",
        fontSize: "0.9rem",
        borderRadius: "6px",
        border: "1px solid var(--text-color)",
        backgroundColor: "var(--bg-color)",
        color: "var(--text-color)",
        cursor: "pointer",
      }}
    >
      {theme === "light" ? "Dark" : "Light"}
    </button>
  );
};

export default ThemeSwitcher;

