import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProviderSetupDialog } from "../../components/settings/ProviderSetupDialog";

vi.mock("../../api", () => ({
  providersApi: {
    getSetupInfo: vi.fn(),
    setup: vi.fn(),
  },
}));

import { providersApi } from "../../api";

const mockedGetSetupInfo = vi.mocked(providersApi.getSetupInfo);
const mockedSetup = vi.mocked(providersApi.setup);

const mockFields = [
  {
    key: "setup_token",
    label: "Setup Token",
    help_text: "Paste your setup token from SimpleFIN Bridge.",
    input_type: "password" as const,
  },
];

describe("ProviderSetupDialog", () => {
  const onClose = vi.fn();
  const onSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetSetupInfo.mockResolvedValue({ data: mockFields } as never);
  });

  it("does not render when isOpen is false", () => {
    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={false}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    expect(screen.queryByText("Configure SimpleFIN")).not.toBeInTheDocument();
  });

  it("renders form fields from setup info", async () => {
    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Setup Token")).toBeInTheDocument();
    });

    expect(screen.getByText(/Paste your setup token/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("submits credentials and shows success", async () => {
    mockedSetup.mockResolvedValue({
      data: {
        provider: "SimpleFIN",
        message: "SimpleFIN configured successfully.",
      },
    } as never);

    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Setup Token")).toBeInTheDocument();
    });

    const input = screen.getByLabelText("Setup Token");
    fireEvent.change(input, { target: { value: "dGVzdA==" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mockedSetup).toHaveBeenCalledWith("SimpleFIN", {
        setup_token: "dGVzdA==",
      });
    });

    await waitFor(() => {
      expect(
        screen.getByText("SimpleFIN configured successfully."),
      ).toBeInTheDocument();
    });

    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("shows error on setup failure", async () => {
    mockedSetup.mockRejectedValue({
      response: { data: { detail: "Failed to exchange setup token" } },
    });

    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Setup Token")).toBeInTheDocument();
    });

    const input = screen.getByLabelText("Setup Token");
    fireEvent.change(input, { target: { value: "bad-token" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(
        screen.getByText("Failed to exchange setup token"),
      ).toBeInTheDocument();
    });

    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("cancel closes dialog", async () => {
    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Setup Token")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows loading state while fetching setup info", () => {
    mockedGetSetupInfo.mockReturnValue(new Promise(() => {}) as never);

    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    expect(screen.getByText("Loading setup info...")).toBeInTheDocument();
  });

  it("shows error when setup info fetch fails", async () => {
    mockedGetSetupInfo.mockRejectedValue({
      response: { data: { detail: "Not found" } },
    });

    render(
      <ProviderSetupDialog
        providerName="SimpleFIN"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Not found")).toBeInTheDocument();
    });
  });
});
