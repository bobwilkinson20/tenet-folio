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

  it("renders IBKR form with two fields", async () => {
    mockedGetSetupInfo.mockResolvedValue({
      data: [
        {
          key: "flex_token",
          label: "Flex Token",
          help_text: "Your Flex Web Service token",
          input_type: "password" as const,
        },
        {
          key: "flex_query_id",
          label: "Flex Query ID",
          help_text: "The numeric ID of your Flex Query",
          input_type: "text" as const,
        },
      ],
    } as never);

    render(
      <ProviderSetupDialog
        providerName="IBKR"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Flex Token")).toBeInTheDocument();
    });

    expect(screen.getByText("Flex Query ID")).toBeInTheDocument();
    expect(screen.getByText("Configure IBKR")).toBeInTheDocument();
  });

  it("shows success with warnings for IBKR setup", async () => {
    mockedGetSetupInfo.mockResolvedValue({
      data: [
        {
          key: "flex_token",
          label: "Flex Token",
          help_text: "Token",
          input_type: "password" as const,
        },
        {
          key: "flex_query_id",
          label: "Flex Query ID",
          help_text: "Query ID",
          input_type: "text" as const,
        },
      ],
    } as never);

    mockedSetup.mockResolvedValue({
      data: {
        provider: "IBKR",
        message: "IBKR configured successfully.",
        warnings: [
          "Trades section is missing recommended columns: buySell, netCash.",
        ],
      },
    } as never);

    render(
      <ProviderSetupDialog
        providerName="IBKR"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Flex Token")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Flex Token"), {
      target: { value: "tok123" },
    });
    fireEvent.change(screen.getByLabelText("Flex Query ID"), {
      target: { value: "456" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(
        screen.getByText("IBKR configured successfully."),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/missing recommended columns.*buySell.*netCash/),
    ).toBeInTheDocument();

    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("renders Coinbase form with textarea for API secret", async () => {
    mockedGetSetupInfo.mockResolvedValue({
      data: [
        {
          key: "api_key",
          label: "API Key",
          help_text: "Your CDP API key",
          input_type: "password" as const,
        },
        {
          key: "api_secret",
          label: "API Secret",
          help_text: "Your ECDSA private key in PEM format",
          input_type: "textarea" as const,
        },
      ],
    } as never);

    render(
      <ProviderSetupDialog
        providerName="Coinbase"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("API Key")).toBeInTheDocument();
    });

    expect(screen.getByText("API Secret")).toBeInTheDocument();
    expect(screen.getByText("Configure Coinbase")).toBeInTheDocument();

    // API Secret field should be a textarea element
    const textarea = screen.getByLabelText("API Secret");
    expect(textarea.tagName).toBe("TEXTAREA");
  });

  it("renders Plaid form with select field for environment", async () => {
    mockedGetSetupInfo.mockResolvedValue({
      data: [
        {
          key: "client_id",
          label: "Client ID",
          help_text: "Your Plaid client_id",
          input_type: "password" as const,
        },
        {
          key: "secret",
          label: "Secret",
          help_text: "Your Plaid secret",
          input_type: "password" as const,
        },
        {
          key: "environment",
          label: "Environment",
          help_text: "Use sandbox for testing",
          input_type: "select" as const,
          options: [
            { value: "sandbox", label: "Sandbox" },
            { value: "production", label: "Production" },
          ],
        },
      ],
    } as never);

    render(
      <ProviderSetupDialog
        providerName="Plaid"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Client ID")).toBeInTheDocument();
    });

    expect(screen.getByText("Secret")).toBeInTheDocument();
    expect(screen.getByText("Environment")).toBeInTheDocument();
    expect(screen.getByText("Configure Plaid")).toBeInTheDocument();

    // Environment field should be a select element
    const select = screen.getByLabelText("Environment");
    expect(select.tagName).toBe("SELECT");

    // Should have the two options
    const options = select.querySelectorAll("option");
    expect(options).toHaveLength(2);
    expect(options[0].textContent).toBe("Sandbox");
    expect(options[1].textContent).toBe("Production");
  });

  it("shows success without warnings for clean IBKR setup", async () => {
    mockedGetSetupInfo.mockResolvedValue({
      data: [
        {
          key: "flex_token",
          label: "Flex Token",
          help_text: "Token",
          input_type: "password" as const,
        },
        {
          key: "flex_query_id",
          label: "Flex Query ID",
          help_text: "Query ID",
          input_type: "text" as const,
        },
      ],
    } as never);

    mockedSetup.mockResolvedValue({
      data: {
        provider: "IBKR",
        message: "IBKR configured successfully.",
        warnings: [],
      },
    } as never);

    render(
      <ProviderSetupDialog
        providerName="IBKR"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Flex Token")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Flex Token"), {
      target: { value: "tok123" },
    });
    fireEvent.change(screen.getByLabelText("Flex Query ID"), {
      target: { value: "456" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(
        screen.getByText("IBKR configured successfully."),
      ).toBeInTheDocument();
    });

    // No warning list should be rendered
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });
});
