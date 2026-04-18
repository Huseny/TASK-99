import { login, logout, me } from "./auth";

// Mock the axios client so tests never touch the network.
vi.mock("./client", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn()
  }
}));

// Import mocked client AFTER vi.mock so the mock is in place.
import { apiClient } from "./client";

const mockPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

describe("auth API – login", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to /auth/login with username and password", async () => {
    const payload = {
      token: "tok-123",
      idle_expires_at: "2026-04-18T00:00:00Z",
      absolute_expires_at: "2026-04-19T00:00:00Z"
    };
    mockPost.mockResolvedValue({ data: payload });

    const result = await login("alice", "SuperSecret12!");

    expect(mockPost).toHaveBeenCalledWith("/auth/login", {
      username: "alice",
      password: "SuperSecret12!"
    });
    expect(result).toEqual(payload);
  });

  it("propagates network errors to the caller", async () => {
    mockPost.mockRejectedValue(new Error("Network Error"));
    await expect(login("alice", "SuperSecret12!")).rejects.toThrow("Network Error");
  });
});

describe("auth API – me", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs /auth/me with the Bearer token in the Authorization header", async () => {
    const profile = { id: 7, username: "alice", role: "ADMIN" };
    mockGet.mockResolvedValue({ data: profile });

    const result = await me("tok-123");

    expect(mockGet).toHaveBeenCalledWith("/auth/me", {
      headers: { Authorization: "Bearer tok-123" }
    });
    expect(result).toEqual(profile);
  });

  it("propagates 401 errors from the server", async () => {
    const err = Object.assign(new Error("Unauthorized"), {
      response: { status: 401 }
    });
    mockGet.mockRejectedValue(err);
    await expect(me("bad-token")).rejects.toThrow("Unauthorized");
  });
});

describe("auth API – logout", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs to /auth/logout with the Bearer token", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await logout("tok-123");

    expect(mockPost).toHaveBeenCalledWith(
      "/auth/logout",
      {},
      { headers: { Authorization: "Bearer tok-123" } }
    );
  });

  it("resolves without returning a value", async () => {
    mockPost.mockResolvedValue({ data: {} });
    const result = await logout("tok-123");
    expect(result).toBeUndefined();
  });
});
