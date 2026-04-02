import { apiClient } from "./client";

export type LoginResponse = {
  token: string;
  idle_expires_at: string;
  absolute_expires_at: string;
};

export type MeResponse = {
  id: number;
  username: string;
  role: string;
  session_idle_expires_at: string;
  session_absolute_expires_at: string;
};

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>("/auth/login", { username, password });
  return response.data;
}

export async function me(token: string): Promise<MeResponse> {
  const response = await apiClient.get<MeResponse>("/auth/me", {
    headers: { Authorization: `Bearer ${token}` }
  });
  return response.data;
}

export async function logout(token: string): Promise<void> {
  await apiClient.post(
    "/auth/logout",
    {},
    {
      headers: { Authorization: `Bearer ${token}` }
    }
  );
}
