"""
humphi/overlay.py — LIVE ticker overlay + Visual guidance system

Phase 1: Shows "🔴 LIVE — AI watching your screen" at top-center.
Phase 3: Visual guidance overlays (highlight boxes, arrows), confidence signals.
"""

import tkinter as tk
import time


class LiveTicker:
    """Small overlay bar showing live session status + confidence signals."""

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.90)
        self._root = root

        sw = root.winfo_screenwidth()
        self.win.geometry(f"420x32+{sw//2 - 210}+4")
        self.win.configure(bg="#dc2626")

        inner = tk.Frame(self.win, bg="#dc2626")
        inner.pack(fill=tk.BOTH, expand=True)

        self.label = tk.Label(inner,
            text="\U0001F534  LIVE — AI watching your screen",
            font=("Segoe UI", 10, "bold"), fg="white", bg="#dc2626",
            padx=12)
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Phase 3: Confidence signal indicator
        self._signal_label = tk.Label(inner, text="",
            font=("Segoe UI", 9, "bold"), fg="white", bg="#dc2626",
            padx=6)
        self._signal_label.pack(side=tk.LEFT)

        self.stop_btn = tk.Button(inner, text="\u25A0 End",
            font=("Segoe UI", 9, "bold"), fg="white", bg="#991b1b",
            bd=0, padx=8, cursor="hand2")
        self.stop_btn.pack(side=tk.RIGHT, padx=4, pady=2)

        # Draggable
        self._dx = self._dy = 0
        self.label.bind("<ButtonPress-1>",
            lambda e: (setattr(self, '_dx', e.x), setattr(self, '_dy', e.y)))
        self.label.bind("<B1-Motion>", lambda e: self.win.geometry(
            f"+{self.win.winfo_x()+e.x-self._dx}+{self.win.winfo_y()+e.y-self._dy}"))

        self.win.withdraw()

        # Phase 3: Guidance overlay window (transparent, click-through)
        self._guide_win = None
        self._guide_items = []  # list of (type, x, y, w, h, color, text)

    def show(self, on_stop=None):
        if on_stop:
            self.stop_btn.config(command=on_stop)
        self.win.deiconify()
        self.win.lift()

    def update_text(self, text):
        self.label.config(text=text)

    def hide(self):
        self.win.withdraw()
        self.hide_guidance()
        self._signal_label.config(text="")

    def get_rect(self):
        try:
            return (self.win.winfo_x(), self.win.winfo_y(),
                    self.win.winfo_width(), self.win.winfo_height())
        except:
            return None

    # ── Phase 3: Confidence Signals ──────────────────────────────────────────

    SIGNALS = {
        "watch":   ("🟢 Watch",   "#22d3a5", "#1a1b26"),
        "prepare": ("🟡 Prepare", "#f5a623", "#1a1b26"),
        "act":     ("🔴 Act Now", "#f7768e", "#ffffff"),
        "clear":   ("",           "#dc2626", "#ffffff"),
    }

    def set_signal(self, signal_type: str):
        """Set a confidence signal: 'watch', 'prepare', 'act', or 'clear'.
        Used for trading alerts or any timed guidance."""
        if signal_type not in self.SIGNALS:
            signal_type = "clear"
        text, bg, fg = self.SIGNALS[signal_type]
        self._signal_label.config(text=text, bg=bg, fg=fg)
        # Flash effect for 'act' signal
        if signal_type == "act":
            self._flash_signal(3)

    def _flash_signal(self, count: int):
        """Flash the signal label for attention."""
        if count <= 0:
            return
        current_bg = self._signal_label.cget("bg")
        flash_bg = "#ffffff" if current_bg != "#ffffff" else "#f7768e"
        self._signal_label.config(bg=flash_bg)
        self._root.after(300, lambda: self._flash_signal(count - 1))

    # ── Phase 3: Visual Guidance Overlay ─────────────────────────────────────

    def show_guidance(self, items: list):
        """Show visual guidance overlays on screen.
        items: list of dicts with keys:
            type: 'highlight' | 'arrow' | 'label'
            x, y: screen coordinates
            w, h: size (for highlight)
            color: hex colour (default #7aa2f7)
            text: label text (for label type)

        Example:
            show_guidance([
                {"type": "highlight", "x": 100, "y": 200, "w": 150, "h": 40, "color": "#9ece6a"},
                {"type": "label", "x": 100, "y": 245, "text": "Click here", "color": "#9ece6a"},
            ])
        """
        self.hide_guidance()
        if not items:
            return

        self._guide_win = tk.Toplevel(self._root)
        self._guide_win.overrideredirect(True)
        self._guide_win.attributes("-topmost", True)
        self._guide_win.attributes("-alpha", 0.65)

        # Cover full screen
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._guide_win.geometry(f"{sw}x{sh}+0+0")

        # Transparent background - use Windows API for click-through
        self._guide_win.configure(bg="black")
        self._guide_win.attributes("-transparentcolor", "black")

        canvas = tk.Canvas(self._guide_win, width=sw, height=sh,
            bg="black", highlightthickness=0)
        canvas.pack()

        for item in items:
            item_type = item.get("type", "highlight")
            x = item.get("x", 0)
            y = item.get("y", 0)
            color = item.get("color", "#7aa2f7")

            if item_type == "highlight":
                w = item.get("w", 100)
                h = item.get("h", 40)
                # Draw highlight rectangle (outline only)
                canvas.create_rectangle(x, y, x+w, y+h,
                    outline=color, width=3, dash=(6, 4))
                # Corner markers for visibility
                m = 8  # marker size
                for cx, cy in [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]:
                    canvas.create_rectangle(cx-m, cy-m, cx+m, cy+m,
                        fill=color, outline="")

            elif item_type == "arrow":
                # Draw an arrow pointing to (x, y) from above
                canvas.create_line(x, y-60, x, y-10,
                    arrow=tk.LAST, arrowshape=(12, 15, 6),
                    fill=color, width=3)

            elif item_type == "label":
                text = item.get("text", "")
                # Text label with background
                canvas.create_rectangle(x-2, y-2, x + len(text)*8 + 12, y+22,
                    fill=color, outline="")
                canvas.create_text(x+6, y+10,
                    text=text, fill="white",
                    font=("Segoe UI", 10, "bold"), anchor=tk.W)

        # Auto-hide after 5 seconds
        self._root.after(5000, self.hide_guidance)

    def hide_guidance(self):
        """Remove all visual guidance overlays."""
        if self._guide_win:
            try:
                self._guide_win.destroy()
            except:
                pass
            self._guide_win = None

    def show_click_here(self, x: int, y: int, text: str = "Click here"):
        """Convenience: show arrow + label at a specific screen position."""
        self.show_guidance([
            {"type": "arrow", "x": x, "y": y, "color": "#9ece6a"},
            {"type": "label", "x": x - 20, "y": y + 5, "text": text, "color": "#9ece6a"},
        ])

    def show_highlight_area(self, x: int, y: int, w: int, h: int,
                            text: str = "", color: str = "#7aa2f7"):
        """Convenience: highlight a rectangular area with optional label."""
        items = [{"type": "highlight", "x": x, "y": y, "w": w, "h": h, "color": color}]
        if text:
            items.append({"type": "label", "x": x, "y": y + h + 4, "text": text, "color": color})
        self.show_guidance(items)
