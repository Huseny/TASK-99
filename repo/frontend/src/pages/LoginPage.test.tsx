import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { LoginPage } from "./LoginPage";

const mockLogin = vi.fn();

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({ login: mockLogin })
}));

describe("LoginPage", () => {
  beforeEach(() => mockLogin.mockReset());

  it("renders username field, password field, and submit button", () => {
    render(<LoginPage onSuccess={() => {}} />);
    expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
    // password input is type=password so no textbox role; query by label text
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("shows field-level validation message when username is blank", () => {
    render(<LoginPage onSuccess={() => {}} />);
    // validation is live; without typing anything the username error is present
    expect(screen.getByText("Username is required.")).toBeInTheDocument();
  });

  it("shows password length error for short passwords", () => {
    render(<LoginPage onSuccess={() => {}} />);
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "tooshort" }
    });
    expect(
      screen.getByText("Password must be at least 12 characters.")
    ).toBeInTheDocument();
  });

  it("shows alert banner when submitting with invalid fields", async () => {
    render(<LoginPage onSuccess={() => {}} />);
    fireEvent.submit(
      screen.getByRole("button", { name: /sign in/i }).closest("form")!
    );
    await waitFor(() => {
      expect(
        screen.getByText("Please fix the highlighted fields and try again.")
      ).toBeInTheDocument();
    });
  });

  it("calls login() and onSuccess when credentials are valid", async () => {
    mockLogin.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    render(<LoginPage onSuccess={onSuccess} />);

    fireEvent.change(screen.getByRole("textbox", { name: /username/i }), {
      target: { value: "admin1" }
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "ValidPassword1!" }
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("admin1", "ValidPassword1!");
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });
});
