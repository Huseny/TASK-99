import { createTheme } from "@mui/material";

export const appTheme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0f4c5c", dark: "#0a3440", light: "#3d7481" },
    secondary: { main: "#e36414", dark: "#b64a0a", light: "#f08a4b" },
    background: {
      default: "#f4f7f5",
      paper: "#ffffff"
    },
    text: {
      primary: "#1f2a30",
      secondary: "#4f5b61"
    },
    success: { main: "#2f7d4b" },
    warning: { main: "#b07808" },
    error: { main: "#b83232" }
  },
  shape: {
    borderRadius: 14
  },
  typography: {
    fontFamily: "'Source Sans 3', 'Segoe UI', sans-serif",
    h1: {
      fontFamily: "'Merriweather', serif",
      fontWeight: 700
    },
    h2: {
      fontFamily: "'Merriweather', serif",
      fontWeight: 700
    },
    h3: {
      fontFamily: "'Merriweather', serif",
      fontWeight: 700
    },
    h4: {
      fontFamily: "'Merriweather', serif",
      fontWeight: 700
    }
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          background:
            "radial-gradient(circle at 15% 20%, rgba(15,76,92,0.13), transparent 40%), radial-gradient(circle at 85% 80%, rgba(227,100,20,0.14), transparent 36%), #f4f7f5"
        }
      }
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 700
        }
      }
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: "0 16px 48px rgba(16, 38, 46, 0.12)"
        }
      }
    }
  }
});
