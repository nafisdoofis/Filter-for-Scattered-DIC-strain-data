A small desktop app (Python, tkinter + matplotlib) for smoothing noisy strain-versus-frame data exported from digital image correlation (DIC) software. It is built for gauge-averaged strain channels from tensile tests, where the data has a clear trend, a lot of frame-to-frame scatter, and a sharp jump at specimen failure.

No code editing is needed: open a file, pick a column, choose a filter, and adjust with sliders and the mouse.

## Features

- **Three filters**
  - Gaussian low-pass filter (frequency domain)
  - Gaussian mean (Gaussian-weighted moving average)
  - Savitzky-Golay (polynomial order and window adjustable)
- **Break-point handling.** Click the plot at the failure frame. The data before and after it are filtered separately, so the sharp drop is not rounded off, the failure jump does not smear into the good data, and the number of data points stays the same.
- **Better edges.** The Gaussian filters pad the ends around straight-line fits of the first and last frames, not a single noisy point, so the curve starts and ends near the local average.
- **Draggable end handles.** Two handles on the red curve (at the start and at the break point) can be dragged up or down with the mouse to correct the ends. The correction fades out smoothly over an adjustable spread.
- **Live plot** with zoom and pan (matplotlib toolbar), plus export of the filtered data (CSV) and the figure (PNG).
- Reads **.xlsx, .xls, .csv and .txt** files; a header row is detected automatically.

## Installation

Requires Python 3.8 or newer.

```bash
pip install numpy scipy pandas matplotlib openpyxl
```

tkinter ships with Python on Windows and macOS. On Linux, install it with `sudo apt install python3-tk`.

## Usage

```bash
python gaussian_lpf_gui.py
```

1. **Data tab:** open your Excel or CSV file and choose the strain column. Click on the plot (or type a frame number) to set the break point. The default is the last frame, so nothing is split until you choose.
2. **Filter tab:** choose a filter and set the strength for the data before the break point and, separately, after it (0 keeps the later data exactly as recorded).
3. **Adjust ends tab (optional):** drag the white handles on the plot, and set how far the adjustment spreads. The toolbar zoom and pan tools must be off for mouse clicks and drags to work. "Reset handles" clears the adjustments.
4. Save the result as CSV (columns: `frame`, `raw`, `filtered`, one row per frame) and the plot as PNG.

### Input format

One column of numeric strain values, one value per frame, in frame order. Rows are indexed from 0 as the frame number. If the file has several numeric columns, you choose one in the app.

### Settings

| Filter | Before-break setting | After-break setting |
|---|---|---|
| Gaussian low-pass | sigma in frames (cutoff f0 = 1 / (2 pi sigma)) | sigma in frames, 0 = keep as recorded |
| Gaussian mean | sigma in frames | sigma in frames, 0 = keep as recorded |
| Savitzky-Golay | window in frames (forced odd) and polynomial order | window in frames, 0 = keep as recorded |

## How it works

- **Gaussian low-pass filter:** the data are transformed with an FFT and multiplied by H(f) = exp(-f^2 / (2 f0^2)), with f0 in cycles per frame, then transformed back. The equivalent Gaussian width in time is sigma = 1 / (2 pi f0) frames.
- **Gaussian mean:** each point is replaced by a Gaussian-weighted average of its neighbours (kernel truncated at 4 sigma). The two Gaussian options give almost the same curve; they are two ways of doing the same smoothing.
- **Savitzky-Golay:** a low-order polynomial is fitted in a sliding window (`scipy.signal.savgol_filter`, edges handled by polynomial interpolation). It keeps slopes and peaks better than a plain average.
- **Ends and break point:** the segment before the break and the segment after it are padded and filtered independently. End handles add a smooth Gaussian-shaped correction to the pre-break segment, and the amount is shown in the app and saved in the CSV.

## Notes and limitations

- The app filters a **one-dimensional strain-versus-frame series** (for example, a virtual-extensometer or gauge-averaged strain). It does not filter full-field strain maps.
- The end handles are a manual, subjective correction. If you use them, state this when reporting results and compare the filtered curve with the raw data.
- Smoothing that is too strong removes real features and rounds off peaks. Choose the lightest filter that gives usable data, and take peak values from the raw data.
- Report the filter type, sigma or window, polynomial order, break point and any handle shifts so the processing can be reproduced.
- Measuring the noise floor on unloaded (zero-strain) frames is recommended before choosing filter settings.

## Background and references

The filter choices follow approaches used in the DIC literature for reducing noise in strain data:

- Amraish, N., Reisinger, A., Pahr, D.H. (2020). Robust Filtering Options for Higher-Order Strain Fields Generated by Digital Image Correlation. *Applied Mechanics*, 1(4), 174-192.
- Baldoni, J., Lionello, G., Zama, F., Cristofolini, L. (2016). Comparison of different filtering strategies to reduce noise in strain measurement with digital image correlation. *Journal of Strain Analysis for Engineering Design*, 51(6), 416-430.
- Savitzky, A., Golay, M.J.E. (1964). Smoothing and differentiation of data by simplified least squares procedures. *Analytical Chemistry*, 36(8), 1627-1639.

The two DIC papers filter spatial strain fields; this tool applies the same ideas to a time (frame) series, so it is an adaptation, not a reproduction of their methods.
