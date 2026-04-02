import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Link,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import { useMemo, useState } from "react";

import { login, me } from "./api/auth";

type FormErrors = {
  username?: string;
  password?: string;
};

function validate(username: string, password: string): FormErrors {
  const errors: FormErrors = {};
  if (!username.trim()) {
    errors.username = "Username is required.";
  }
  if (!password) {
    errors.password = "Password is required.";
  } else if (password.length < 12) {
    errors.password = "Password must be at least 12 characters.";
  }
  return errors;
}

export function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [profile, setProfile] = useState<{ username: string; role: string } | null>(null);

  const errors = useMemo(() => validate(username, password), [username, password]);
  const hasErrors = Boolean(errors.username || errors.password);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitMessage(null);
    setSubmitError(null);

    if (hasErrors) {
      setSubmitError("Please fix the highlighted fields and try again.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await login(username.trim(), password);
      localStorage.setItem("cems_token", result.token);
      const currentUser = await me(result.token);
      setProfile({ username: currentUser.username, role: currentUser.role });
      setSubmitMessage(`Signed in as ${currentUser.username}.`);
    } catch (error: unknown) {
      const status = typeof error === "object" && error && "response" in error ? (error as { response?: { status?: number; data?: { detail?: string } } }).response?.status : undefined;
      const detail = typeof error === "object" && error && "response" in error ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail : undefined;
      if (status === 423) {
        setSubmitError(detail ?? "Your account is locked due to repeated failed attempts.");
      } else if (status === 401) {
        setSubmitError("Invalid credentials. Please verify and try again.");
      } else {
        setSubmitError(detail ?? "Unable to sign in right now. Please try again shortly.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        p: { xs: 2, md: 4 }
      }}
    >
      <Grid container spacing={3} sx={{ maxWidth: 1080 }}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card
            sx={{
              height: "100%",
              borderRadius: 4,
              background: "linear-gradient(160deg, #0f4c5c 0%, #184f60 55%, #2f6672 100%)",
              color: "#f4f7f5",
              position: "relative",
              overflow: "hidden"
            }}
          >
            <CardContent sx={{ p: { xs: 3, md: 5 } }}>
              <Stack spacing={2.5}>
                <Chip
                  label="Air-gapped deployment"
                  size="small"
                  sx={{
                    width: "fit-content",
                    backgroundColor: "rgba(255,255,255,0.18)",
                    color: "#ffffff",
                    fontWeight: 600
                  }}
                />
                <Typography variant="h3" lineHeight={1.2}>
                  Collegiate Enrollment & Assessment Management
                </Typography>
                <Typography variant="body1" sx={{ color: "rgba(244,247,245,0.9)", maxWidth: 580 }}>
                  Manage enrollment rounds, assessment workflows, financial settlement, and governance controls in one secure local platform.
                </Typography>
                <Grid container spacing={1.5} sx={{ pt: 1 }}>
                  {[
                    "Student and staff role portals",
                    "Review scoring and outlier workflows",
                    "Immutable audit and operational logs",
                    "Offline in-app notifications"
                  ].map((item) => (
                    <Grid size={{ xs: 12, sm: 6 }} key={item}>
                      <Box
                        sx={{
                          p: 1.5,
                          borderRadius: 2,
                          backgroundColor: "rgba(255,255,255,0.14)",
                          border: "1px solid rgba(255,255,255,0.22)"
                        }}
                      >
                        <Typography variant="body2" fontWeight={600}>
                          {item}
                        </Typography>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 5 }}>
          <Card sx={{ borderRadius: 4 }}>
            <CardContent sx={{ p: { xs: 3, md: 4 } }}>
              <Stack spacing={2.25} component="form" onSubmit={handleSubmit} noValidate>
                <Typography variant="h4" color="primary.dark">
                  Welcome Back
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Sign in with your university account credentials.
                </Typography>

                <TextField
                  label="Username"
                  fullWidth
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  error={Boolean(errors.username)}
                  helperText={errors.username}
                  autoComplete="username"
                />
                <TextField
                  label="Password"
                  type="password"
                  fullWidth
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  error={Boolean(errors.password)}
                  helperText={errors.password ?? "Minimum 12 characters."}
                  autoComplete="current-password"
                />

                {submitError && <Alert severity="error">{submitError}</Alert>}
                {submitMessage && <Alert severity="success">{submitMessage}</Alert>}
                {profile && (
                  <Alert severity="info">
                    Active role: <strong>{profile.role}</strong>
                  </Alert>
                )}

                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disableElevation
                  disabled={submitting}
                  startIcon={submitting ? <CircularProgress color="inherit" size={16} /> : undefined}
                >
                  {submitting ? "Signing in..." : "Sign In"}
                </Button>

                <Typography variant="caption" color="text.secondary" textAlign="center">
                  Need access help? Contact your system administrator.
                </Typography>
              </Stack>
            </CardContent>
          </Card>

          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2, textAlign: "center" }}>
            By signing in, you agree to local governance and audit policies. <Link href="#" underline="hover">Learn more</Link>
          </Typography>
        </Grid>
      </Grid>
    </Box>
  );
}
