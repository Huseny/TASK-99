import { fireEvent, render, screen } from "@testing-library/react";

import { AppShell } from "./AppShell";

const defaultProps = {
  title: "My App",
  subtitle: "Welcome",
  navItems: [
    { label: "Dashboard", active: true, onClick: vi.fn() },
    { label: "Settings", onClick: vi.fn() },
  ],
  unreadCount: 3,
  onNotificationsClick: vi.fn(),
  onLogout: vi.fn(),
  children: <div>Main content</div>,
};

beforeEach(() => vi.clearAllMocks());

describe("AppShell", () => {
  it("renders title and subtitle in the toolbar", () => {
    render(<AppShell {...defaultProps} />);
    expect(screen.getByText("My App")).toBeInTheDocument();
    expect(screen.getByText("Welcome")).toBeInTheDocument();
  });

  it("renders nav item labels in the sidebar", () => {
    render(<AppShell {...defaultProps} />);
    // Both permanent and temporary drawers render nav items
    expect(screen.getAllByText("Dashboard").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Settings").length).toBeGreaterThan(0);
  });

  it("renders children in the main content area", () => {
    render(<AppShell {...defaultProps} />);
    expect(screen.getByText("Main content")).toBeInTheDocument();
  });

  it("shows the unread badge count", () => {
    render(<AppShell {...defaultProps} unreadCount={7} />);
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("calls onNotificationsClick when the notifications button is clicked", () => {
    const onNotificationsClick = vi.fn();
    render(<AppShell {...defaultProps} onNotificationsClick={onNotificationsClick} />);
    fireEvent.click(screen.getByRole("button", { name: "open notifications" }));
    expect(onNotificationsClick).toHaveBeenCalledTimes(1);
  });

  it("calls onLogout when the logout button is clicked", () => {
    const onLogout = vi.fn();
    render(<AppShell {...defaultProps} onLogout={onLogout} />);
    fireEvent.click(screen.getByRole("button", { name: "logout" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("calls the nav item's onClick when clicked", () => {
    const navOnClick = vi.fn();
    render(
      <AppShell
        {...defaultProps}
        navItems={[{ label: "Reports", onClick: navOnClick }]}
      />
    );
    const items = screen.getAllByText("Reports");
    fireEvent.click(items[0]);
    expect(navOnClick).toHaveBeenCalledTimes(1);
  });

  it("renders CEMS Portal branding in the sidebar", () => {
    render(<AppShell {...defaultProps} />);
    expect(screen.getAllByText("CEMS Portal").length).toBeGreaterThan(0);
  });
});
