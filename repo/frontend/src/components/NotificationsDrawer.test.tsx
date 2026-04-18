import { fireEvent, render, screen } from "@testing-library/react";

import { NotificationsDrawer } from "./NotificationsDrawer";

const ITEMS = [
  {
    id: 1,
    title: "Unread notice",
    message: "Round update available",
    read: false,
    delivered_at: "2026-04-10T10:00:00Z"
  },
  {
    id: 2,
    title: "Already read",
    message: "Assignment posted",
    read: true,
    delivered_at: "2026-04-09T08:00:00Z"
  }
];

describe("NotificationsDrawer", () => {
  it("renders notification titles when open", () => {
    render(
      <NotificationsDrawer
        open
        items={ITEMS}
        onClose={() => {}}
        onMarkRead={() => {}}
      />
    );
    expect(screen.getByText("Unread notice")).toBeInTheDocument();
    expect(screen.getByText("Already read")).toBeInTheDocument();
  });

  it("shows the empty-state placeholder when there are no items", () => {
    render(
      <NotificationsDrawer
        open
        items={[]}
        onClose={() => {}}
        onMarkRead={() => {}}
      />
    );
    expect(screen.getByText("No notifications yet")).toBeInTheDocument();
  });

  it("calls onMarkRead with the item id when an unread item is clicked", () => {
    const onMarkRead = vi.fn();
    render(
      <NotificationsDrawer
        open
        items={ITEMS}
        onClose={() => {}}
        onMarkRead={onMarkRead}
      />
    );
    fireEvent.click(screen.getByText("Unread notice"));
    expect(onMarkRead).toHaveBeenCalledWith(1);
    expect(onMarkRead).toHaveBeenCalledTimes(1);
  });

  it("does not call onMarkRead when an already-read item is clicked", () => {
    const onMarkRead = vi.fn();
    render(
      <NotificationsDrawer
        open
        items={ITEMS}
        onClose={() => {}}
        onMarkRead={onMarkRead}
      />
    );
    fireEvent.click(screen.getByText("Already read"));
    expect(onMarkRead).not.toHaveBeenCalled();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <NotificationsDrawer
        open
        items={[]}
        onClose={onClose}
        onMarkRead={() => {}}
      />
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not show notification content when closed", () => {
    render(
      <NotificationsDrawer
        open={false}
        items={ITEMS}
        onClose={() => {}}
        onMarkRead={() => {}}
      />
    );
    expect(screen.queryByText("Unread notice")).not.toBeInTheDocument();
  });
});
