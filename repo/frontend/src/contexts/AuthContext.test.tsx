import { act, renderHook, waitFor } from "@testing-library/react";

import { AuthProvider, useAuth } from "./AuthContext";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  me: vi.fn(),
  logout: vi.fn(),
}));

import { login as loginApi, logout as logoutApi, me as meApi } from "../api/auth";
const mockLogin = loginApi as ReturnType<typeof vi.fn>;
const mockMe = meApi as ReturnType<typeof vi.fn>;
const mockLogout = logoutApi as ReturnType<typeof vi.fn>;

const PROFILE = {
  id: 1,
  username: "alice",
  role: "STUDENT" as const,
  session_idle_expires_at: "2099-01-01T00:00:00Z",
  session_absolute_expires_at: "2099-01-01T00:00:00Z",
};

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("AuthContext – bootstrap with no stored token", () => {
  it("resolves bootstrapping with no user when localStorage is empty", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isBootstrapping).toBe(false));
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(mockMe).not.toHaveBeenCalled();
  });
});

describe("AuthContext – bootstrap with stored token", () => {
  it("restores the session and sets user when a valid token is in localStorage", async () => {
    localStorage.setItem("cems_token", "stored-tok");
    mockMe.mockResolvedValue(PROFILE);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).toEqual(PROFILE));

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe("stored-tok");
    expect(mockMe).toHaveBeenCalledWith("stored-tok");
  });

  it("clears the invalid token and stays unauthenticated when /me rejects", async () => {
    localStorage.setItem("cems_token", "expired-tok");
    mockMe.mockRejectedValue(new Error("Unauthorized"));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isBootstrapping).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem("cems_token")).toBeNull();
  });
});

describe("AuthContext – login", () => {
  it("stores the token, fetches the profile, and marks authenticated", async () => {
    mockLogin.mockResolvedValue({
      token: "new-tok",
      idle_expires_at: "2099-01-01T00:00:00Z",
      absolute_expires_at: "2099-01-01T00:00:00Z",
    });
    mockMe.mockResolvedValue(PROFILE);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isBootstrapping).toBe(false));

    await act(async () => {
      await result.current.login("alice", "secret-passw0rd");
    });

    expect(mockLogin).toHaveBeenCalledWith("alice", "secret-passw0rd");
    expect(localStorage.getItem("cems_token")).toBe("new-tok");
    expect(result.current.user).toEqual(PROFILE);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("propagates login API errors to the caller", async () => {
    mockLogin.mockRejectedValue(Object.assign(new Error(), { response: { status: 401 } }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isBootstrapping).toBe(false));

    await expect(
      act(async () => {
        await result.current.login("alice", "wrong-passw0rd!!");
      })
    ).rejects.toBeDefined();

    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem("cems_token")).toBeNull();
  });
});

describe("AuthContext – logout", () => {
  it("clears token, user, and localStorage after successful logout", async () => {
    localStorage.setItem("cems_token", "tok");
    mockMe.mockResolvedValue(PROFILE);
    mockLogout.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    await act(async () => {
      await result.current.logout();
    });

    expect(mockLogout).toHaveBeenCalledWith("tok");
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem("cems_token")).toBeNull();
  });

  it("still clears local state even when the logout API call fails", async () => {
    localStorage.setItem("cems_token", "tok");
    mockMe.mockResolvedValue(PROFILE);
    mockLogout.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem("cems_token")).toBeNull();
  });
});

describe("useAuth outside provider", () => {
  it("throws when called outside AuthProvider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within AuthProvider"
    );
    consoleError.mockRestore();
  });
});
