import React from "react";
import { Link, useLocation } from "react-router-dom";

export interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const navLinks = [
    { path: "/", label: "Dashboard" },
    { path: "/accounts", label: "Accounts" },
    { path: "/cashflows", label: "Cash Flows" },
    { path: "/settings", label: "Settings" },
  ];

  return (
    <div className="min-h-screen bg-tf-bg-primary text-tf-text-primary">
      <header className="border-b border-tf-border-subtle bg-tf-bg-surface">
        <div className="px-10 py-4">
          <div className="flex items-center justify-between">
            <Link to="/">
              <img
                src="/lockup-h-dark.svg"
                alt="TenetFolio"
                className="h-8"
              />
            </Link>
            <nav className="flex gap-4">
              {navLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`rounded-md px-3 py-2 text-[13px] font-medium transition-colors ${
                    location.pathname === link.path
                      ? "border border-tf-accent-border bg-tf-accent-muted text-tf-accent-hover"
                      : "text-tf-text-secondary hover:bg-tf-bg-elevated hover:text-tf-text-primary"
                  }`}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      </header>
      <main className="px-10 py-8">{children}</main>
      <footer className="mt-12 border-t border-tf-border-subtle bg-tf-bg-surface">
        <div className="px-10 py-4">
          <p className="text-[11px] text-tf-text-tertiary">TenetFolio</p>
        </div>
      </footer>
    </div>
  );
}
