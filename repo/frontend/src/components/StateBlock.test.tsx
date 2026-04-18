import { render, screen } from "@testing-library/react";

import { ErrorBlock, LoadingBlock } from "./StateBlock";

describe("LoadingBlock", () => {
  it("renders the given label", () => {
    render(<LoadingBlock label="Fetching data…" />);
    expect(screen.getByText("Fetching data…")).toBeInTheDocument();
  });

  it("renders a progress indicator", () => {
    render(<LoadingBlock label="Loading" />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("renders different labels independently", () => {
    const { unmount } = render(<LoadingBlock label="First" />);
    expect(screen.getByText("First")).toBeInTheDocument();
    unmount();
    render(<LoadingBlock label="Second" />);
    expect(screen.getByText("Second")).toBeInTheDocument();
  });
});

describe("ErrorBlock", () => {
  it("renders the error message", () => {
    render(<ErrorBlock message="Something went wrong" />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("renders as an alert element", () => {
    render(<ErrorBlock message="Oops" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders different messages independently", () => {
    const { unmount } = render(<ErrorBlock message="Error A" />);
    expect(screen.getByText("Error A")).toBeInTheDocument();
    unmount();
    render(<ErrorBlock message="Error B" />);
    expect(screen.getByText("Error B")).toBeInTheDocument();
  });
});
