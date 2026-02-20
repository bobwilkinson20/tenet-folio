import "@testing-library/jest-dom";

// Polyfill ResizeObserver for Headless UI components
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
