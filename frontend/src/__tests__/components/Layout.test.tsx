import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import { Layout } from "../../components/layout/Layout";

function renderLayout(initialRoute = "/") {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Layout>
        <p>Test content</p>
      </Layout>
    </MemoryRouter>,
  );
}

describe("Layout", () => {
  it("renders logo with correct alt text and src", () => {
    renderLayout();

    const logo = screen.getByAltText("TenetFolio");
    expect(logo).toBeInTheDocument();
    expect(logo).toHaveAttribute("src", "/lockup-h-dark.svg");
  });

  it("logo links to /", () => {
    renderLayout("/accounts");

    const logoLink = screen.getByAltText("TenetFolio").closest("a");
    expect(logoLink).toHaveAttribute("href", "/");
  });

  it("renders all 3 nav links", () => {
    renderLayout();

    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Accounts" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("highlights active nav link for Dashboard at /", () => {
    renderLayout("/");

    const dashboardLink = screen.getByRole("link", { name: "Dashboard" });
    expect(dashboardLink.className).toContain("bg-tf-accent-muted");
    expect(dashboardLink.className).toContain("text-tf-accent-hover");

    const accountsLink = screen.getByRole("link", { name: "Accounts" });
    expect(accountsLink.className).toContain("text-tf-text-secondary");
    expect(accountsLink.className).not.toContain("bg-tf-accent-muted");
  });

  it("highlights active nav link for Accounts at /accounts", () => {
    renderLayout("/accounts");

    const accountsLink = screen.getByRole("link", { name: "Accounts" });
    expect(accountsLink.className).toContain("bg-tf-accent-muted");
    expect(accountsLink.className).toContain("text-tf-accent-hover");

    const dashboardLink = screen.getByRole("link", { name: "Dashboard" });
    expect(dashboardLink.className).toContain("text-tf-text-secondary");
  });

  it("renders children in main area", () => {
    renderLayout();

    expect(screen.getByText("Test content")).toBeInTheDocument();
  });

  it("renders footer with brand name", () => {
    renderLayout();

    expect(screen.getByText("TenetFolio")).toBeInTheDocument();
  });
});
