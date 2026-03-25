"""
humphi/overlay.py — LIVE ticker overlay

Shows "🔴 LIVE — AI watching your screen" at top-center.
Click-through, always on top, draggable.
"""

import tkinter as tk


class LiveTicker:
    """Small overlay bar showing live session status."""

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.90)

        sw = root.winfo_screenwidth()
        self.win.geometry(f"340x32+{sw//2 - 170}+4")
        self.win.configure(bg="#dc2626")

        inner = tk.Frame(self.win, bg="#dc2626")
        inner.pack(fill=tk.BOTH, expand=True)

        self.label = tk.Label(inner,
            text="\U0001F534  LIVE — AI watching your screen",
            font=("Segoe UI", 10, "bold"), fg="white", bg="#dc2626",
            padx=12)
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)

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

    def show(self, on_stop=None):
        if on_stop:
            self.stop_btn.config(command=on_stop)
        self.win.deiconify()
        self.win.lift()

    def update_text(self, text):
        self.label.config(text=text)

    def hide(self):
        self.win.withdraw()

    def get_rect(self):
        try:
            return (self.win.winfo_x(), self.win.winfo_y(),
                    self.win.winfo_width(), self.win.winfo_height())
        except:
            return None
