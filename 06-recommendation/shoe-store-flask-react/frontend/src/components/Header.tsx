import React from "react";
import ThemeSwitcher from "./ThemeSwitcher";
import './Header.css'; // Import the CSS file

const Header = () => {
  return (
    <header className="header">
      <h1>Db2 X Q's</h1>
      <p>The style of your life</p>

      <div className="theme-switcher">
        <ThemeSwitcher />
      </div>
    </header>
  );
};

export default Header;
