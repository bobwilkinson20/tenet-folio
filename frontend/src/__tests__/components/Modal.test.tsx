import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Modal } from "@/components/common/Modal";

describe("Modal", () => {
  it("renders children when open", () => {
    render(
      <Modal isOpen={true}>
        <p>Hello</p>
      </Modal>
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("returns null when closed", () => {
    const { container } = render(
      <Modal isOpen={false}>
        <p>Hello</p>
      </Modal>
    );
    expect(container.innerHTML).toBe("");
  });

  it("calls onClose when backdrop is clicked", () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={onClose}>
        <p>Content</p>
      </Modal>
    );
    // Click the backdrop (outermost div)
    const backdrop = screen.getByText("Content").parentElement!.parentElement!;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose when content is clicked", () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={onClose}>
        <p>Content</p>
      </Modal>
    );
    fireEvent.click(screen.getByText("Content"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("applies default max-w-md class", () => {
    render(
      <Modal isOpen={true}>
        <p>Content</p>
      </Modal>
    );
    const card = screen.getByText("Content").parentElement!;
    expect(card.className).toContain("max-w-md");
  });

  it("applies custom maxWidth class", () => {
    render(
      <Modal isOpen={true} maxWidth="lg">
        <p>Content</p>
      </Modal>
    );
    const card = screen.getByText("Content").parentElement!;
    expect(card.className).toContain("max-w-lg");
  });

  it("does not error when onClose is omitted and backdrop is clicked", () => {
    render(
      <Modal isOpen={true}>
        <p>Content</p>
      </Modal>
    );
    const backdrop = screen.getByText("Content").parentElement!.parentElement!;
    expect(() => fireEvent.click(backdrop)).not.toThrow();
  });
});
