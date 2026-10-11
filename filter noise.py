"""
Filter for noisy DIC strain data (desktop app): Gaussian low-pass, Gaussian mean, Savitzky-Golay.

Run:      python gaussian_lpf_gui.py
Install:  pip install numpy scipy pandas matplotlib openpyxl
          (tkinter comes with Python on Windows/macOS; on Linux: sudo apt install python3-tk)

How to use:
  1. Data tab: open your Excel/CSV file, pick the strain column, then click on the plot (or type a
     frame number) to set the BREAK POINT. The data before and after it are filtered separately,
     so the sharp drop is not rounded off and the number of data points stays the same.
  2. Filter tab: choose a filter and drag the sliders until the red curve follows the trend.
  3. Adjust ends tab (optional): drag the white handles on the plot up or down to correct the
     start (and the end before the break point). The change fades out smoothly over the
     "adjustment spread". Zoom/pan tools in the toolbar must be switched off.
  4. Save the data as CSV (all frames, raw + filtered) and the plot as PNG.

Gaussian filters use padding around straight-line fits of the first/last points (not a single
noisy sample), so the ends of the curve follow the local average.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

METHODS = ["Gaussian low-pass (LPF)", "Gaussian mean", "Savitzky-Golay"]


def _pad_fit(y, K):
    """Pad K points at each end by odd reflection about straight-line fits of the end points."""
    y = np.asarray(y, dtype=float)
    m = min(len(y), max(10, K))
    xs = np.arange(m)
    a0 = np.polyval(np.polyfit(xs, y[:m], 1), 0)          # fitted value at the first point
    b0 = np.polyval(np.polyfit(xs, y[-m:], 1), m - 1)     # fitted value at the last point
    left = 2 * a0 - y[1:K + 1][::-1]
    right = 2 * b0 - y[-K - 1:-1][::-1]
    return np.concatenate([left, y, right])


def gaussian_lpf(y, f0):
    """Gaussian low-pass filter in the frequency domain. f0 in cycles/frame."""
    y = np.asarray(y, dtype=float)
    pad = min(int(np.ceil(5 / (2 * np.pi * f0))), len(y) - 1)
    yp = _pad_fit(y, pad)                                  # avoids edge ringing and edge bias
    H = np.exp(-np.fft.rfftfreq(len(yp)) ** 2 / (2 * f0 ** 2))
    out = np.fft.irfft(np.fft.rfft(yp) * H, n=len(yp))
    return out[pad:pad + len(y)]


def gaussian_mean(y, sigma):
    """Gaussian-weighted moving average (time-domain Gaussian filter)."""
    y = np.asarray(y, dtype=float)
    K = min(int(np.ceil(4 * sigma)), len(y) - 1)
    k = np.arange(-K, K + 1)
    w = np.exp(-k ** 2 / (2 * sigma ** 2))
    w /= w.sum()
    return np.convolve(_pad_fit(y, K), w, mode="valid")


def sg_filter(y, window, order):
    """Savitzky-Golay filter (needs scipy). Window is forced odd and limited to the data length."""
    from scipy.signal import savgol_filter
    y = np.asarray(y, dtype=float)
    window = int(window)
    if window % 2 == 0:
        window += 1
    if window > len(y):
        window = len(y) if len(y) % 2 else len(y) - 1
    if window < 3:
        return y
    return savgol_filter(y, window, min(order, window - 1), mode="interp")


def apply_filter(y, method, p, order):
    """p = sigma (frames) for the Gaussian filters, window (frames) for Savitzky-Golay."""
    if method == "Savitzky-Golay":
        return sg_filter(y, p, order)
    if method == "Gaussian mean":
        return gaussian_mean(y, p)
    return gaussian_lpf(y, 1 / (2 * np.pi * p))


def filter_to_break(y, n_filter, method, p, p_post, order):
    """Filter the points before the break with p and the points after it separately with
    p_post (0 = keep them exactly as recorded). The two segments never mix, so the failure
    jump cannot smear backwards and stays steep. Output length = input length."""
    out = np.asarray(y, dtype=float).copy()
    out[:n_filter] = apply_filter(out[:n_filter], method, p, order)
    if p_post > 0 and len(out) - n_filter >= 3:
        out[n_filter:] = apply_filter(out[n_filter:], method, p_post, order)
    return out


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Filter for DIC strain data")
        self.geometry("1050x650")
        self.columns = {}      # column name -> numpy array of valid numbers
        self.series = None     # selected column
        self.col_name = ""
        self.y = self.f = self.f_base = None
        self.bp = 0            # last frame filtered with the "before break" settings
        self.off_start = self.off_end = 0.0   # handle adjustments (data units)
        self.drag = None
        self._build()

    # ---------------- layout ----------------
    def _build(self):
        side = ttk.Frame(self, padding=8)
        side.pack(side="left", fill="y")
        nb = ttk.Notebook(side)
        nb.pack(fill="x")
        t1, t2, t3 = (ttk.Frame(nb, padding=10) for _ in range(3))
        nb.add(t1, text="1. Data")
        nb.add(t2, text="2. Filter")
        nb.add(t3, text="3. Adjust ends")
        gray = {"wraplength": 270, "foreground": "gray"}

        # tab 1: data
        ttk.Button(t1, text="Open Excel / CSV file...", command=self.open_file).pack(fill="x")
        self.file_lbl = ttk.Label(t1, text="No file loaded", **gray)
        self.file_lbl.pack(anchor="w", pady=(2, 8))
        ttk.Label(t1, text="Strain column").pack(anchor="w")
        self.combo = ttk.Combobox(t1, state="readonly", width=34)
        self.combo.pack(fill="x")
        self.combo.bind("<<ComboboxSelected>>", self.pick_column)
        ttk.Label(t1, text="Break point (frame where the specimen fails)").pack(anchor="w", pady=(10, 2))
        self.last_var = tk.StringVar()
        entry = ttk.Entry(t1, textvariable=self.last_var)
        entry.pack(fill="x")
        entry.bind("<Return>", self.refresh)
        entry.bind("<FocusOut>", self.refresh)
        ttk.Label(t1, text="Click on the plot, or type a frame and press Enter. Data before and after "
                           "it are filtered separately (sharp drop kept, same number of data points).",
                  **gray).pack(anchor="w")

        # tab 2: filter
        self.method = ttk.Combobox(t2, state="readonly", values=METHODS)
        self.method.current(0)
        self.method.pack(fill="x")
        self.method.bind("<<ComboboxSelected>>", self.on_method)
        self.scale = tk.Scale(t2, orient="horizontal", resolution=1, command=self.refresh)
        self.scale.pack(fill="x", pady=(6, 0))
        self.scale_post = tk.Scale(t2, orient="horizontal", resolution=1, command=self.refresh)
        self.scale_post.pack(fill="x", pady=(6, 0))
        self.order = tk.IntVar(value=2)
        self.order_row = ttk.Frame(t2)
        ttk.Label(self.order_row, text="Polynomial order").pack(side="left")
        ttk.Spinbox(self.order_row, from_=1, to=5, width=4, textvariable=self.order,
                    command=self.refresh).pack(side="left", padx=6)
        self.hint = ttk.Label(t2, text="", **gray)
        self.hint.pack(anchor="w", pady=(4, 0))

        # tab 3: adjust ends
        ttk.Label(t3, text="Drag the white handles on the plot up or down to correct the start and "
                           "the end before the break point (zoom/pan tools must be off). The change "
                           "fades out over the spread below.", **gray).pack(anchor="w")
        self.spread = tk.Scale(t3, from_=10, to=500, resolution=1, orient="horizontal",
                               label="Adjustment spread (frames)", command=self.refresh)
        self.spread.set(60)
        self.spread.pack(fill="x", pady=(6, 0))
        ttk.Button(t3, text="Reset handles", command=self.reset_offsets).pack(fill="x", pady=4)

        # info + save (always visible)
        self.info = ttk.Label(side, text="", wraplength=290, justify="left")
        self.info.pack(anchor="w", pady=8)
        ttk.Button(side, text="Save filtered data (CSV)...", command=self.save_csv).pack(fill="x", pady=2)
        ttk.Button(side, text="Save plot (PNG)...", command=self.save_plot).pack(fill="x", pady=2)

        right = ttk.Frame(self)
        right.pack(side="right", fill="both", expand=True)
        self.fig = Figure(figsize=(6, 4.5), dpi=100, constrained_layout=True)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.toolbar = NavigationToolbar2Tk(self.canvas, right)
        self.toolbar.update()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.draw_empty()
        self.on_method()

    def draw_empty(self):
        self.ax.clear()
        self.ax.text(0.5, 0.5, "Open a file to begin", ha="center", va="center",
                     transform=self.ax.transAxes, color="gray")
        self.canvas.draw_idle()

    # ---------------- data loading ----------------
    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel or CSV", "*.xlsx *.xls *.csv *.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            if path.lower().endswith((".xlsx", ".xls")):
                raw = pd.read_excel(path, header=None)
            else:
                raw = pd.read_csv(path, header=None, sep=None, engine="python")
        except Exception as e:
            messagebox.showerror("Could not read file", str(e))
            return

        first = raw.iloc[0]
        has_header = any(pd.notna(v) and pd.isna(pd.to_numeric(v, errors="coerce")) for v in first)
        data = raw.iloc[1:] if has_header else raw
        self.columns = {}
        for i in range(raw.shape[1]):
            name = str(first.iloc[i]).strip() if has_header and pd.notna(first.iloc[i]) else f"Column {i + 1}"
            vals = pd.to_numeric(data.iloc[:, i], errors="coerce").dropna().to_numpy(dtype=float)
            if len(vals) >= 3:
                self.columns[name] = vals
        if not self.columns:
            messagebox.showwarning("No data", "No numeric column with at least 3 values was found.")
            return

        self.file_lbl.config(text=path.replace("\\", "/").split("/")[-1], foreground="black")
        self.combo["values"] = list(self.columns)
        self.combo.current(0)
        self.pick_column()

    def pick_column(self, *_):
        self.col_name = self.combo.get()
        self.series = self.columns[self.col_name]
        self.last_var.set(str(len(self.series) - 1))
        self.off_start = self.off_end = 0.0
        self.refresh()

    # ---------------- filter settings ----------------
    def on_method(self, *_):
        """Switch slider meaning/ranges when the filter method changes."""
        m = self.method.get()
        if m == "Savitzky-Golay":
            self.scale.config(from_=5, to=401, label="Before break: window (frames, odd)")
            self.scale.set(101)
            self.scale_post.config(from_=0, to=61, label="After break: window (0 = keep as recorded)")
            self.scale_post.set(11)
            self.order_row.pack(fill="x", pady=(6, 0), before=self.hint)
            self.hint.config(text="Fits a low-order polynomial in a sliding window, so slopes and peaks "
                                  "are kept better than with a plain average. Order 2-3 is usual; the "
                                  "window must be larger than the order.")
        else:
            self.scale.config(from_=1, to=200, label="Before break: Gaussian width sigma (frames)")
            self.scale.set(16)
            self.scale_post.config(from_=0, to=20, label="After break: sigma (0 = keep as recorded)")
            self.scale_post.set(3)
            self.order_row.pack_forget()
            if m == "Gaussian mean":
                self.hint.config(text="Replaces each point by a Gaussian-weighted average of its neighbours. "
                                      "Higher sigma = smoother. Gives almost the same curve as the low-pass "
                                      "version.")
            else:
                self.hint.config(text="Removes fast scatter in the frequency domain, cutoff f0 = 1/(2*pi*sigma). "
                                      "Higher sigma = smoother. Lower it if the red curve looks flatter than "
                                      "your real data.")
        self.off_start = self.off_end = 0.0
        self.refresh()

    # ---------------- filtering and plotting ----------------
    def apply_offsets(self):
        """self.f = filtered curve + the smooth corrections set by dragging the two handles."""
        f = self.f_base.copy()
        if self.off_start or self.off_end:
            L = float(self.spread.get())
            i = np.arange(self.bp + 1)
            f[:self.bp + 1] += (self.off_start * np.exp(-i ** 2 / (2 * L ** 2))
                                + self.off_end * np.exp(-(self.bp - i) ** 2 / (2 * L ** 2)))
        self.f = f

    def reset_offsets(self, *_):
        self.off_start = self.off_end = 0.0
        self.refresh()

    def refresh(self, *_):
        if self.series is None:
            return
        total = len(self.series)
        try:
            bp = int(float(self.last_var.get()))
        except ValueError:
            bp = total - 1
        bp = max(2, min(bp, total - 1))     # last frame that gets the "before break" filter

        method = self.method.get()
        p = float(self.scale.get())
        p_post = float(self.scale_post.get())
        try:
            order = int(self.order.get())
        except (ValueError, tk.TclError):
            order = 2
        self.y = self.series
        self.bp = bp
        self.f_base = filter_to_break(self.y, bp + 1, method, p, p_post, order)
        self.apply_offsets()

        if method == "Savitzky-Golay":
            setting = f"window {p:.0f} frames, order {order}"
            post_txt = f"window {p_post:.0f}" if p_post >= 3 else "kept as recorded"
        else:
            setting = f"sigma {p:.0f} frames (f0 = {1 / (2 * np.pi * p):.4f} cycles/frame)"
            post_txt = f"sigma {p_post:.0f}" if p_post > 0 else "kept as recorded"
        noise = float(np.sqrt(np.mean((self.y[:bp + 1] - self.f[:bp + 1]) ** 2)))
        self.info.config(text=(f"{total} data points (all kept)\n"
                               f"{method}\n"
                               f"Before break: frames 0-{bp}, {setting}\n"
                               f"After break: frames {bp + 1}-{total - 1}, {post_txt}\n"
                               f"Handle shifts: start {self.off_start:+.4g}, end {self.off_end:+.4g}\n"
                               f"Noise removed before break (RMS raw - filtered): {noise:.4g}"))

        self.ax.clear()
        self.ax.plot(self.y, color="0.7", lw=0.8, label="raw")
        self.line_f, = self.ax.plot(self.f, color="tab:red", lw=1.8, label="filtered")
        self.ax.axvline(bp, color="k", ls="--", lw=1, label="break point")
        self.handles, = self.ax.plot([0, bp], [self.f[0], self.f[bp]], "o", ms=9, mfc="white",
                                     mec="tab:red", mew=2, zorder=5, label="drag to adjust")
        self.ax.set_xlabel("Frame")
        self.ax.set_ylabel(self.col_name)
        self.ax.grid(alpha=0.3)
        self.ax.legend()
        self.canvas.draw_idle()

    # ---------------- mouse ----------------
    def _near_handle(self, event):
        for name, x in (("start", 0), ("end", self.bp)):
            px, py = self.ax.transData.transform((x, self.f[x]))
            if abs(event.x - px) < 14 and abs(event.y - py) < 14:
                return name
        return None

    def on_click(self, event):
        """Click a white handle to drag it; click elsewhere on the plot to set the break point.
        Only works while the toolbar zoom/pan tools are off."""
        if self.series is None or self.f is None or event.inaxes is not self.ax or event.xdata is None:
            return
        if str(self.toolbar.mode):
            return
        handle = self._near_handle(event)
        if handle:
            self.drag = handle
            return
        self.last_var.set(str(int(round(event.xdata))))
        self.refresh()

    def on_motion(self, event):
        if not self.drag or event.ydata is None:
            return
        L = float(self.spread.get())
        cross = np.exp(-self.bp ** 2 / (2 * L ** 2))     # small overlap between the two corrections
        if self.drag == "start":
            self.off_start = event.ydata - self.f_base[0] - self.off_end * cross
        else:
            self.off_end = event.ydata - self.f_base[self.bp] - self.off_start * cross
        self.apply_offsets()
        self.line_f.set_ydata(self.f)
        self.handles.set_ydata([self.f[0], self.f[self.bp]])
        self.canvas.draw_idle()

    def on_release(self, event):
        if self.drag:
            self.drag = None
            self.refresh()

    # ---------------- saving ----------------
    def save_csv(self):
        if self.y is None:
            messagebox.showinfo("Nothing to save", "Load data first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile="filtered_strain.csv")
        if path:
            pd.DataFrame({"frame": np.arange(len(self.y)), "raw": self.y,
                          "filtered": self.f}).to_csv(path, index=False)

    def save_plot(self):
        if self.y is None:
            messagebox.showinfo("Nothing to save", "Load data first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")],
                                            initialfile="filtered_strain.png")
        if path:
            self.fig.savefig(path, dpi=200)


if __name__ == "__main__":
    App().mainloop()
