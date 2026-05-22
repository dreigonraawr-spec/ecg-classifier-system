"""
ECG Intelligent Monitoring Software  v2.0
==========================================
Biomedical Electronics - Final Assignment (Group 1)

v2.0 additions:
  + Patient information panel
  + Live scrolling ECG (animated real-time display)  [blit-accelerated]
  + Multi-lead display (Lead I, II, III, aVF, aVR)
  + Arrhythmia detection (AFib, PVCs, missed beats)
  + ST-segment analysis (elevation / depression)
  + QRS duration measurement
  + Extended HRV: SDNN, RMSSD, pNN50
  + ECG paper grid (1 mm / 5 mm standard grid)
  + Sound alerts for critical/abnormal events
  + Session history log
  + Clinical PDF report export
  + Animated heartbeat splash screen on startup
"""

import sys, os, threading, math, time
from datetime import datetime

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

try:
    import winsound as _ws
    def _beep(critical=False):
        f, d = (1400, 600) if critical else (880, 250)
        threading.Thread(target=lambda: _ws.Beep(f, d), daemon=True).start()
except ImportError:
    def _beep(critical=False): pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Heavy modules are imported lazily inside main() so the splash screen
# can appear before numpy / matplotlib / scipy finish loading.
np = pd = matplotlib = Figure = FigureCanvasTkAgg = NavigationToolbar2Tk = None
PdfPages = butter = filtfilt = find_peaks = welch = None

# ═══════════════════════════════════════════════════════════════════════════
#  CLINICAL THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════
HR_CRITICAL_LOW  = 40
HR_BRADYCARDIA   = 60
HR_TACHYCARDIA   = 100
HR_CRITICAL_HIGH = 150
ST_ELEV_THR      =  0.10   # mV
ST_DEPR_THR      = -0.05   # mV
QRS_WIDE_THR     = 140.0   # ms  (>120 ms clinical; 140 avoids false positives on simulated data)
AFIB_CV_THR      =  0.15   # RR coefficient of variation

# ═══════════════════════════════════════════════════════════════════════════
#  CARDIBEART COLOUR PALETTE  —  soft dark navy, easy on the eyes
# ═══════════════════════════════════════════════════════════════════════════
C_BG      = '#161c2d'   # window background — deep navy (not pitch black)
C_PANEL   = '#1d2340'   # sidebar / header panels
C_CARD    = '#252d4a'   # card / widget surfaces
C_BORDER  = '#38426a'   # dividers and borders
C_TEXT    = '#dde4f5'   # primary text — cool white
C_SUBTEXT = '#8090b8'   # secondary / hint text
C_ACCENT  = '#5c8bea'   # periwinkle-blue accent
C_GREEN   = '#3dd68c'   # normal / success
C_YELLOW  = '#f5a522'   # warning / amber
C_RED     = '#e55a5a'   # critical / alert (softer than pure red)
C_ORANGE  = '#f07838'   # tachycardia / high-HR
C_ECG     = '#29d9b8'   # ECG trace — teal (medical, legible, not neon)
C_FILT    = '#5c8bea'   # filtered signal
C_PEAKS   = '#e8587a'   # R-peak markers — rose
C_GRID_MJ = '#1c2b44'   # major ECG paper grid (blue-tinted)
C_GRID_MN = '#171f35'   # minor ECG paper grid

FONT_TITLE  = ('Segoe UI', 15, 'bold')
FONT_HEADER = ('Segoe UI', 11, 'bold')
FONT_BODY   = ('Segoe UI', 10)
FONT_SMALL  = ('Segoe UI',  9)
FONT_MONO   = ('Consolas',  9)
FONT_BIG    = ('Segoe UI', 26, 'bold')
FONT_HUGE   = ('Segoe UI', 42, 'bold')


# ═══════════════════════════════════════════════════════════════════════════
#  ANIMATED HEARTBEAT SPLASH SCREEN
# ═══════════════════════════════════════════════════════════════════════════
class SplashScreen:
    """
    Full-screen-centered splash with a continuously animating ECG heartbeat
    line.  Uses only tkinter (no numpy/matplotlib) so it appears immediately
    while the heavy scientific libraries are loading in a background thread.
    """

    _W, _H = 560, 320
    _WAVE  = None   # pre-computed once, shared across instances

    # ── waveform pre-computation (pure Python math, no numpy) ───────────────
    @classmethod
    def _build_wave(cls):
        if cls._WAVE is not None:
            return
        n = 240   # points per beat
        beat = []
        for i in range(n):
            t = i / n
            def g(c, w, a):
                return a * math.exp(-((t - c) ** 2) / (2 * w ** 2))
            y = (g(0.15, 0.025,  0.15) +   # P
                 g(0.27, 0.010, -0.08) +   # Q
                 g(0.30, 0.015,  1.00) +   # R
                 g(0.33, 0.012, -0.18) +   # S
                 g(0.47, 0.050,  0.28))    # T
            beat.append(y)
        cls._WAVE = beat * 4   # tile 4 beats for seamless looping

    # ── constructor ──────────────────────────────────────────────────────────
    def __init__(self, root):
        self._build_wave()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)   # borderless window
        self.win.configure(bg=C_BG)
        self.win.attributes('-topmost', True)

        # Center on screen
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{self._W}x{self._H}+{(sw-self._W)//2}+{(sh-self._H)//2}")

        # ── border frame ──
        bd = tk.Frame(self.win, bg=C_BORDER, padx=1, pady=1)
        bd.pack(fill='both', expand=True)
        inner = tk.Frame(bd, bg=C_BG)
        inner.pack(fill='both', expand=True)

        # ── title block ──
        tk.Frame(inner, bg=C_BG, height=16).pack()
        brand = tk.Frame(inner, bg=C_BG)
        brand.pack()
        tk.Label(brand, text="♥", bg=C_BG, fg=C_ECG,
                 font=('Segoe UI', 20)).pack(side='left', padx=(0, 6))
        tk.Label(brand, text="CardiBeat",
                 bg=C_BG, fg=C_TEXT,
                 font=('Segoe UI', 18, 'bold')).pack(side='left')
        tk.Label(inner,
                 text="Intelligent ECG Monitoring  |  Group 1",
                 bg=C_BG, fg=C_SUBTEXT,
                 font=('Segoe UI', 9)).pack(pady=(3, 0))

        # ── ECG canvas ──
        self.cv = tk.Canvas(inner, width=520, height=110,
                            bg=C_BG, highlightthickness=0)
        self.cv.pack(pady=12)

        # ── status label ──
        self.status_var = tk.StringVar(value="Starting up…")
        tk.Label(inner, textvariable=self.status_var,
                 bg=C_BG, fg=C_SUBTEXT,
                 font=('Segoe UI', 9)).pack()

        # ── bottom accent bar ──
        tk.Frame(inner, bg=C_ACCENT, height=2).pack(fill='x', side='bottom')
        tk.Label(inner, text="v2.0",
                 bg=C_BG, fg=C_BORDER,
                 font=('Segoe UI', 8)).pack(side='bottom', pady=4)

        self._phase  = 0
        self._job    = None
        self._closed = False
        self._animate()
        self.win.update()

    # ── animation loop ───────────────────────────────────────────────────────
    def _animate(self):
        if self._closed or not self.win.winfo_exists():
            return

        CW, CH  = 520, 110
        cy, amp = CH // 2 + 8, 40
        wave    = self._WAVE
        n       = len(wave)

        # advance phase (scroll speed)
        self._phase = (self._phase + 4) % n

        # build canvas coordinate list
        coords = []
        for px in range(CW):
            idx = (self._phase + int(px * n / CW)) % n
            py  = cy - int(wave[idx] * amp)
            coords += [px, py]

        self.cv.delete('all')

        # dim trailing portion — dark teal ghost
        if len(coords) >= 4:
            self.cv.create_line(*coords, fill='#0b2e2a', width=1, tags='ecg')

        # bright leading portion (last ~80 px)
        tail_start = max(0, CW - 80) * 2
        if len(coords) > tail_start + 4:
            self.cv.create_line(*coords[tail_start:],
                                fill='#1fbda0', width=2, tags='ecg')

        # vivid tip + glow rings
        if len(coords) >= 2:
            lx, ly = coords[-2], coords[-1]
            for r, col in [(9, '#071a17'), (6, '#0e2c28'),
                           (4, '#177a6a'), (2, '#29d9b8')]:
                self.cv.create_oval(lx - r, ly - r, lx + r, ly + r,
                                    fill=col, outline='', tags='ecg')

        self._job = self.win.after(35, self._animate)

    # ── public API ───────────────────────────────────────────────────────────
    def set_status(self, text):
        if not self._closed and self.win.winfo_exists():
            self.status_var.set(text)
            self.win.update_idletasks()

    def close(self):
        self._closed = True
        if self._job:
            try: self.win.after_cancel(self._job)
            except Exception: pass
        try:
            if self.win.winfo_exists():
                self.win.destroy()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  SIGNAL PROCESSING ENGINE
# ═══════════════════════════════════════════════════════════════════════════
class ECGProcessor:

    # ── Simulation ──────────────────────────────────────────────────────────
    @staticmethod
    def _beat(fs, hr):
        """
        Generate one PQRST beat with absolute-time component widths so that
        QRS duration (~90 ms) is independent of heart rate.
        """
        dur   = 60.0 / hr
        t     = np.linspace(0, dur, int(fs * dur), endpoint=False)
        r_pos = 0.32 * dur          # R peak at 32% of beat duration

        def g(dt, w, a):            # dt and w are in seconds
            return a * np.exp(-((t - (r_pos + dt)) ** 2) / (2 * w ** 2))

        ecg  = g(-0.150, 0.022,  0.15)   # P  : 150 ms before R
        ecg += g(-0.030, 0.010, -0.08)   # Q  :  30 ms before R
        ecg += g( 0.000, 0.016,  1.00)   # R  :  at R peak
        ecg += g( 0.030, 0.012, -0.18)   # S  :  30 ms after R
        ecg += g( 0.150, 0.050,  0.28)   # T  : 150 ms after R
        return ecg

    @classmethod
    def simulate(cls, duration=10.0, fs=500, hr=75.0, noise=0.05, arrhythmia='none'):
        """
        arrhythmia:
          'none'   — normal sinus rhythm  (±3 % jitter)
          'afib'   — atrial fibrillation  (±35 % random RR → CV ≈ 0.20)
          'pvc'    — premature ventricular complex every 5–6 beats
                     + compensatory pause, detectable as premature beats
          'missed' — dropped beat every 7 beats (long pause > 175 % mean RR)
        """
        n          = int(duration * fs)
        segments   = []
        beat_count = 0

        while sum(len(s) for s in segments) < n + int(2 * fs):
            beat_count += 1

            if arrhythmia == 'afib':
                # Completely irregular rhythm — RR varies ±35 %
                jitter = 1.0 + np.random.uniform(-0.35, 0.35)

            elif arrhythmia == 'pvc':
                # Every 6th beat is an early PVC (RR = 65 % of normal)
                # followed by a compensatory pause (RR = 135 %)
                cycle = beat_count % 6
                if cycle == 0:
                    jitter = 0.65      # early PVC
                elif cycle == 1:
                    jitter = 1.35      # compensatory pause
                else:
                    jitter = 1.0 + np.random.uniform(-0.03, 0.03)

            elif arrhythmia == 'missed':
                # Every 7th beat is missing — represented as a doubled RR interval
                if beat_count % 7 == 0:
                    jitter = 2.0       # pause = two beat lengths
                else:
                    jitter = 1.0 + np.random.uniform(-0.03, 0.03)

            else:
                jitter = 1.0 + np.random.uniform(-0.03, 0.03)

            segments.append(cls._beat(fs, hr * max(jitter, 0.3)))

        ecg = np.concatenate(segments)[:n]
        ecg += noise * np.random.randn(n)
        return np.linspace(0, duration, n, endpoint=False), ecg

    # ── Lead Derivation ─────────────────────────────────────────────────────
    @staticmethod
    def derive_leads(lead_i):
        """Approximate Lead II, III, aVF, aVR from Lead I."""
        ii  =  1.40 * lead_i
        iii =  ii - lead_i              # Einthoven: III = II − I
        avf = (ii + iii) / 2.0
        avr = -(lead_i + ii) / 2.0
        return ii, iii, avf, avr

    # ── Filtering ───────────────────────────────────────────────────────────
    @staticmethod
    def bandpass(ecg, fs, low=0.5, high=40.0, order=4):
        nyq  = fs / 2.0
        b, a = butter(order, [max(low/nyq, 1e-4), min(high/nyq, 0.99)], btype='band')
        return filtfilt(b, a, ecg)

    # ── R-Peak Detection ────────────────────────────────────────────────────
    @staticmethod
    def detect_rpeaks(ecg, fs, min_rr_ms=300.0):
        peaks, _ = find_peaks(ecg,
                               height=0.45 * np.max(ecg),
                               distance=int(min_rr_ms * fs / 1000.0))
        return peaks

    # ── Heart Rate ──────────────────────────────────────────────────────────
    @staticmethod
    def heart_rate(r_peaks, fs):
        if r_peaks is None or len(r_peaks) < 2:
            return None, np.array([])
        rr = np.diff(r_peaks) / float(fs)
        return float(np.mean(60.0 / rr)), 60.0 / rr

    # ── Classification ──────────────────────────────────────────────────────
    @staticmethod
    def classify(hr):
        if hr is None: return "Undetected", "error"
        if hr < HR_CRITICAL_LOW:  return f"Critical Bradycardia ({hr:.0f} bpm)", "critical"
        if hr < HR_BRADYCARDIA:   return f"Bradycardia  ({hr:.0f} bpm)", "low"
        if hr <= HR_TACHYCARDIA:  return f"Normal Sinus Rhythm  ({hr:.0f} bpm)", "normal"
        if hr <= HR_CRITICAL_HIGH:return f"Tachycardia  ({hr:.0f} bpm)", "high"
        return f"Critical Tachycardia ({hr:.0f} bpm)", "critical"

    # ── Signal Quality ──────────────────────────────────────────────────────
    @staticmethod
    def signal_quality(ecg):
        if len(ecg) == 0:              return "Empty signal", False
        if np.var(ecg) < 1e-8:        return "Flatline detected", False
        if np.max(np.abs(ecg)) > 15:  return "Extreme amplitude / lead-off", False
        if np.mean(ecg >= 0.995*np.max(ecg)) > 0.02: return "Signal clipping", False
        w      = max(3, int(len(ecg)*0.005))
        smooth = np.convolve(ecg, np.ones(w)/w, mode='same')
        snr    = 10*np.log10(np.var(ecg)/(np.var(ecg-smooth)+1e-12))
        if snr < 5: return f"High noise  (SNR {snr:.1f} dB)", False
        return f"Acceptable  (SNR {snr:.1f} dB)", True

    # ── Arrhythmia Detection ────────────────────────────────────────────────
    @staticmethod
    def detect_arrhythmia(r_peaks, fs):
        out = dict(afib=False, premature=0, missed=0, irregular=False, cv=0.0, messages=[])
        if r_peaks is None or len(r_peaks) < 4:
            out['messages'] = ['Insufficient beats for arrhythmia analysis']
            return out
        rr   = np.diff(r_peaks) / fs * 1000.0
        mean = np.mean(rr)
        cv   = float(np.std(rr) / mean)
        afib = cv > AFIB_CV_THR
        pre  = int(np.sum(rr < 0.75 * mean))
        mis  = int(np.sum(rr > 1.75 * mean))
        irr  = afib or pre > 0 or mis > 0
        msgs = []
        if afib: msgs.append(f'Possible Atrial Fibrillation  (RR CV={cv:.2f})')
        if pre:  msgs.append(f'{pre} premature beat(s)  (PVC/PAC)')
        if mis:  msgs.append(f'{mis} long pause(s) / missed beat(s)')
        if not irr: msgs.append('Regular rhythm — no arrhythmia detected')
        out.update(afib=afib, premature=pre, missed=mis, irregular=irr, cv=cv, messages=msgs)
        return out

    # ── ST Segment ──────────────────────────────────────────────────────────
    @staticmethod
    def analyze_st(ecg, r_peaks, fs):
        """
        Measure ST deviation at J+80 ms relative to PR-segment baseline.
        Thresholds are scaled to R-peak amplitude so the method works for
        both normalised simulated signals and real mV-scaled ECG data.
        """
        empty = dict(mean_st=None, elevation=False, depression=False,
                     message='Insufficient data')
        if r_peaks is None or len(r_peaks) < 2: return empty

        r_amp  = float(np.mean(ecg[r_peaks]))       # mean R-peak amplitude
        st_off = int(0.060 * fs)                     # ST measure: J+60 ms after R
        vals   = []
        for rp in r_peaks:
            sp = rp + st_off
            if sp >= len(ecg): continue
            # PR-segment baseline: 90–60 ms before R (after P end, before Q onset)
            b0 = max(0, rp - int(0.090 * fs))
            b1 = max(b0 + 1, rp - int(0.060 * fs))
            vals.append(ecg[sp] - np.mean(ecg[b0:b1]))
        if not vals: return empty

        st   = float(np.mean(vals))
        # Scale thresholds: 10% / 5% of mean R amplitude
        elev_thr = max(ST_ELEV_THR, 0.10 * r_amp)
        depr_thr = min(ST_DEPR_THR, -0.05 * r_amp)
        elev = st >  elev_thr
        depr = st <  depr_thr
        # Report in normalised units and as % of R amplitude
        pct  = st / r_amp * 100.0 if r_amp > 0 else 0.0
        if elev:  msg = f'ST Elevation: {st:+.3f} ({pct:+.1f}% of R)  *** Possible MI ***'
        elif depr:msg = f'ST Depression: {st:+.3f} ({pct:+.1f}% of R)  — Possible ischemia'
        else:     msg = f'ST Normal: {st:+.3f} ({pct:+.1f}% of R)'
        return dict(mean_st=st, elevation=elev, depression=depr, message=msg)

    # ── QRS Duration ────────────────────────────────────────────────────────
    @staticmethod
    def measure_qrs(ecg, r_peaks, fs):
        """
        Measure QRS duration using zero-crossing approach:
        onset = last zero-crossing before R (Q wave start),
        offset = first return to zero after S wave dip.
        """
        if r_peaks is None or len(r_peaks) == 0: return None, 'No R-peaks'
        hw   = int(0.18 * fs)   # 180 ms search window
        durs = []
        for rp in r_peaks:
            # QRS onset: last zero-crossing going left from R
            L = max(0, rp - hw)
            for i in range(rp, max(0, rp - hw), -1):
                if ecg[i] <= 0.0:
                    L = i; break
            # QRS offset: S wave dip then return to >= 0 (cap at 100 ms after R)
            right_hw = min(hw, int(0.10 * fs))
            R = min(len(ecg) - 1, rp + right_hw)
            went_neg = False
            for i in range(rp, min(len(ecg) - 1, rp + right_hw)):
                if ecg[i] < 0:
                    went_neg = True
                elif went_neg and ecg[i] >= 0.0:
                    R = i; break
            d = (R - L) / fs * 1000.0
            if 30 < d < 250: durs.append(d)
        if not durs: return None, 'Could not measure QRS'
        m = float(np.mean(durs))
        msg = (f'Wide QRS: {m:.0f} ms  — possible bundle branch block'
               if m > QRS_WIDE_THR else f'Normal QRS: {m:.0f} ms  (80–120 ms)')
        return m, msg

    # ── Cardiac Health Score ────────────────────────────────────────────────
    @staticmethod
    def health_score(sev, hrv, arrh, st):
        """
        Synthesise a 0–100 cardiac health score from four clinical domains:

          HR severity   (30 pts)  — normal=30, brad/tachy=15, critical=0
          HRV / SDNN    (25 pts)  — ≥50ms=25, ≥30ms=15, ≥15ms=8, <15ms=0
          Arrhythmia    (25 pts)  — none=25, minor=15, moderate=8, AFib/major=3
          ST segment    (20 pts)  — normal=20, depression=10, elevation=0
        """
        # HR domain
        hr_pts = {'normal': 30, 'low': 15, 'high': 15,
                  'critical': 0, 'error': 0}.get(sev, 0)

        # HRV domain
        sdnn = hrv.get('sdnn') if hrv else None
        if sdnn is None:
            hrv_pts = 12   # neutral — no data
        elif sdnn >= 50:  hrv_pts = 25
        elif sdnn >= 30:  hrv_pts = 15
        elif sdnn >= 15:  hrv_pts = 8
        else:             hrv_pts = 0

        # Arrhythmia domain
        if not arrh.get('irregular'):
            arr_pts = 25
        elif arrh.get('afib'):
            arr_pts = 3
        elif (arrh.get('premature', 0) + arrh.get('missed', 0)) <= 2:
            arr_pts = 15
        else:
            arr_pts = 8

        # ST domain
        if st.get('elevation'):    st_pts = 0
        elif st.get('depression'): st_pts = 10
        else:                      st_pts = 20

        total = hr_pts + hrv_pts + arr_pts + st_pts
        return min(100, max(0, total))

    @staticmethod
    def health_grade(score):
        if score >= 80: return "Excellent", C_GREEN
        if score >= 60: return "Good",      '#5ecb96'
        if score >= 40: return "Fair",      C_YELLOW
        if score >= 20: return "Poor",      C_ORANGE
        return               "Critical",   C_RED

    # ── HRV Full ────────────────────────────────────────────────────────────
    @staticmethod
    def hrv_full(r_peaks, fs):
        if r_peaks is None or len(r_peaks) < 3:
            return dict(sdnn=None, rmssd=None, pnn50=None)
        rr   = np.diff(r_peaks) / fs * 1000.0
        drr  = np.diff(rr)
        return dict(
            sdnn =float(np.std(rr)),
            rmssd=float(np.sqrt(np.mean(drr**2))),
            pnn50=float(np.sum(np.abs(drr)>50) / max(len(drr),1) * 100))

    # ── Poincaré Plot Metrics ───────────────────────────────────────────────
    @staticmethod
    def poincare_metrics(r_peaks, fs):
        """SD1 (short-term) and SD2 (long-term) from Poincaré plot geometry."""
        if r_peaks is None or len(r_peaks) < 4:
            return dict(sd1=None, sd2=None, sd_ratio=None)
        rr      = np.diff(r_peaks) / fs * 1000.0
        diff_rr = np.diff(rr)
        sum_rr  = rr[:-1] + rr[1:]
        sd1 = float(np.std(diff_rr) / np.sqrt(2))
        sd2 = float(np.std(sum_rr)  / np.sqrt(2))
        return dict(sd1=sd1, sd2=sd2, sd_ratio=sd1/sd2 if sd2 > 0 else None)

    # ── Frequency-Domain HRV ────────────────────────────────────────────────
    @staticmethod
    def hrv_freq(r_peaks, fs):
        """LF / HF power via Welch PSD on a 4 Hz-interpolated RR tachogram."""
        if r_peaks is None or len(r_peaks) < 8:
            return dict(lf=None, hf=None, lf_hf=None, tp=None)
        rr_ms = np.diff(r_peaks) / fs * 1000.0
        t_rr  = (r_peaks[:-1] + r_peaks[1:]) * 0.5 / fs
        fs_i  = 4.0
        t_uni = np.arange(t_rr[0], t_rr[-1], 1.0 / fs_i)
        if len(t_uni) < 16:
            return dict(lf=None, hf=None, lf_hf=None, tp=None)
        rr_i  = np.interp(t_uni, t_rr, rr_ms)
        rr_i -= np.mean(rr_i)
        nperseg = min(len(rr_i), max(32, len(rr_i) // 2))
        freqs, psd = welch(rr_i, fs=fs_i, nperseg=nperseg)
        # np.trapz removed in NumPy 2.0; fall back gracefully
        _trapz = getattr(np, 'trapezoid', getattr(np, 'trapz', None))
        def _bp(f0, f1):
            m = (freqs >= f0) & (freqs < f1)
            return float(_trapz(psd[m], freqs[m])) if m.any() else 0.0
        lf, hf, tp = _bp(0.04, 0.15), _bp(0.15, 0.40), _bp(0.00, 0.40)
        return dict(lf=lf, hf=hf, lf_hf=lf/hf if hf > 1e-10 else None, tp=tp)

    # ── PR Interval ─────────────────────────────────────────────────────────
    @staticmethod
    def measure_pr(ecg, r_peaks, fs):
        """Estimate PR interval: P-wave onset to R-peak.  Normal 120–200 ms."""
        if r_peaks is None or len(r_peaks) == 0:
            return None, 'No R-peaks'
        durs = []
        for rp in r_peaks:
            w0 = max(0, rp - int(0.22 * fs))
            w1 = max(0, rp - int(0.06 * fs))
            if w1 - w0 < 3:
                continue
            seg   = ecg[w0:w1]
            p_rel = int(np.argmax(seg))
            p_abs = w0 + p_rel
            p_amp = float(ecg[p_abs])
            bl    = float(np.mean(ecg[max(0, w0 - int(0.03*fs)):w0 + 2]))
            thr   = bl + 0.15 * max(p_amp - bl, 1e-6)
            p_onset = p_abs
            for i in range(p_abs, max(0, p_abs - int(0.08*fs)), -1):
                if ecg[i] <= thr:
                    p_onset = i; break
            pr = (rp - p_onset) / fs * 1000.0
            if 60 < pr < 350:
                durs.append(pr)
        if not durs:
            return None, 'Could not measure PR interval'
        m = float(np.mean(durs))
        if m < 120:   msg = f'Short PR: {m:.0f} ms  — possible pre-excitation (WPW)'
        elif m > 200: msg = f'Long PR: {m:.0f} ms  — possible 1st-degree AV block'
        else:         msg = f'Normal PR: {m:.0f} ms  (120–200 ms)'
        return m, msg


# ═══════════════════════════════════════════════════════════════════════════
#  VALIDATION CASES
# ═══════════════════════════════════════════════════════════════════════════
VALIDATION_CASES = {
    "Normal Sinus Rhythm (72 bpm)":   dict(hr=72,  noise=0.04, duration=10, expect='normal',   eq=True),
    "Bradycardia (45 bpm)":            dict(hr=45,  noise=0.04, duration=15, expect='low',      eq=True),
    "Tachycardia (130 bpm)":           dict(hr=130, noise=0.04, duration=10, expect='high',     eq=True),
    "Critical Bradycardia (35 bpm)":   dict(hr=35,  noise=0.04, duration=20, expect='critical', eq=True),
    "Critical Tachycardia (160 bpm)":  dict(hr=160, noise=0.04, duration=10, expect='critical', eq=True),
    "High Noise / Artefact":           dict(hr=72,  noise=0.65, duration=10, expect='normal',   eq=False),
}


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════
class ECGMonitorApp:

    def __init__(self, master):
        self.master = master
        self.master.title("CardiBeat  v2.0  —  Intelligent ECG Monitoring  |  Group 1")
        self.master.geometry("1480x900")
        self.master.minsize(1200, 750)
        self.master.configure(bg=C_BG)

        # analysis state
        self.time_data    = None
        self.raw_ecg      = None
        self.filtered_ecg = None
        self.r_peaks      = None
        self.mean_hr      = None
        self.hr_array     = np.array([])
        self.fs           = 500
        self.last_results = {}   # stores full analysis for PDF / analysis tab

        # live ECG state
        self._live_running     = False
        self._live_after_id    = None
        self._live_buf         = np.zeros(0)
        self._live_fs          = 250
        self._live_chunk       = 12   # samples per 50 ms update
        self._live_hr_val      = 72.0
        self._live_frame_count = 0
        self._live_bg          = None
        self._live_beat_count  = 0
        self._live_q           = np.zeros(0)   # beat queue (samples)
        self._live_q_pos       = 0             # total samples ever dequeued
        self._live_r_at        = []            # upcoming R-peak absolute positions

        # history
        self.history = []   # list of dicts

        self._build_header()
        self._build_notebook()
        self._build_statusbar()
        self._bind_shortcuts()

    # ══════════════════════════════════════════════════════════════════════
    #  HEADER
    # ══════════════════════════════════════════════════════════════════════
    def _build_header(self):
        hdr = tk.Frame(self.master, bg=C_PANEL, height=60)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)

        # ── brand mark ────────────────────────────────────────────────────
        tk.Label(hdr, text="♥", bg=C_PANEL, fg=C_ECG,
                 font=('Segoe UI', 18), padx=14).pack(side='left', pady=10)
        tk.Label(hdr, text="CardiBeat",
                 bg=C_PANEL, fg=C_TEXT,
                 font=('Segoe UI', 16, 'bold')).pack(side='left', pady=10)
        tk.Label(hdr, text="  Intelligent ECG Monitoring",
                 bg=C_PANEL, fg=C_SUBTEXT,
                 font=('Segoe UI', 9)).pack(side='left', pady=10)

        # thin vertical separator
        tk.Frame(hdr, bg=C_BORDER, width=1).pack(side='left', fill='y',
                                                   padx=14, pady=14)
        tk.Label(hdr, text="v2.0",
                 bg=C_PANEL, fg=C_BORDER,
                 font=('Segoe UI', 9)).pack(side='left', pady=10)

        # ── right side ────────────────────────────────────────────────────
        tk.Label(hdr, text="Biomedical Electronics  |  Group 1",
                 bg=C_PANEL, fg=C_BORDER,
                 font=FONT_SMALL, padx=14).pack(side='right', pady=10)
        self.lbl_clock = tk.Label(hdr, text="", bg=C_PANEL, fg=C_SUBTEXT,
                                   font=FONT_SMALL, padx=14)
        self.lbl_clock.pack(side='right', pady=10)

        # thin accent line at very bottom of header
        tk.Frame(hdr, bg=C_ACCENT, height=2).pack(fill='x', side='bottom')
        self._tick()

    def _tick(self):
        self.lbl_clock.config(text=datetime.now().strftime("%Y-%m-%d   %H:%M:%S"))
        self.master.after(1000, self._tick)

    # ══════════════════════════════════════════════════════════════════════
    #  NOTEBOOK
    # ══════════════════════════════════════════════════════════════════════
    def _build_notebook(self):
        s = ttk.Style()
        s.theme_use('default')
        s.configure('ECG.TNotebook', background=C_BG, borderwidth=0,
                    tabmargins=[0, 0, 0, 0])
        s.configure('ECG.TNotebook.Tab', background=C_PANEL, foreground=C_SUBTEXT,
                    padding=(18, 8), font=FONT_BODY)
        s.map('ECG.TNotebook.Tab',
              background=[('selected', C_CARD), ('active', C_BORDER)],
              foreground=[('selected', C_TEXT), ('active', C_TEXT)])

        self.nb = ttk.Notebook(self.master, style='ECG.TNotebook')
        self.nb.pack(fill='both', expand=True)

        self._build_monitor_tab()
        self._build_live_tab()
        self._build_multilead_tab()
        self._build_analysis_tab()
        self._build_history_tab()
        self._build_validation_tab()
        self._build_about_tab()

        # Auto-refresh dependent tabs when the user switches to them
        self.nb.bind('<<NotebookTabChanged>>', self._on_tab_change)

    def _on_tab_change(self, event):
        tab = self.nb.tab(self.nb.select(), 'text').strip()
        if tab == 'Multi-Lead':
            self._plot_multilead()
        elif tab == 'Clinical Analysis':
            if not self.last_results:
                self._show_ca_placeholder()

    def _build_statusbar(self):
        tk.Frame(self.master, bg=C_BORDER, height=1).pack(fill='x', side='bottom')
        bar = tk.Frame(self.master, bg=C_PANEL, height=26)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)
        self.status_var = tk.StringVar(value="CardiBeat ready — generate a simulated ECG or load a CSV to begin.")
        self.status_lbl = tk.Label(bar, textvariable=self.status_var, bg=C_PANEL, fg=C_SUBTEXT,
                                    font=FONT_SMALL, anchor='w', padx=14)
        self.status_lbl.pack(fill='x', pady=3)

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 1 — MONITOR
    # ══════════════════════════════════════════════════════════════════════
    def _build_monitor_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  ♥  Monitor  ")

        # ── left sidebar — scrollable so all controls are always reachable ──
        sidebar_outer = tk.Frame(frame, bg=C_PANEL, width=284)
        sidebar_outer.pack(side='left', fill='y')
        sidebar_outer.pack_propagate(False)

        _sb_scroll = tk.Scrollbar(sidebar_outer, orient='vertical')
        _sb_scroll.pack(side='right', fill='y')

        _sb_canvas = tk.Canvas(sidebar_outer, bg=C_PANEL, highlightthickness=0,
                               yscrollcommand=_sb_scroll.set)
        _sb_canvas.pack(side='left', fill='both', expand=True)
        _sb_scroll.config(command=_sb_canvas.yview)

        ctrl = tk.Frame(_sb_canvas, bg=C_PANEL)
        _ctrl_win = _sb_canvas.create_window((0, 0), window=ctrl, anchor='nw')

        def _on_ctrl_resize(event):
            _sb_canvas.configure(scrollregion=_sb_canvas.bbox('all'))
            _sb_canvas.itemconfig(_ctrl_win, width=_sb_canvas.winfo_width())
        ctrl.bind('<Configure>', _on_ctrl_resize)
        _sb_canvas.bind('<Configure>',
                        lambda e: _sb_canvas.itemconfig(_ctrl_win, width=e.width))

        def _mwheel(event):
            _sb_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        for w in (sidebar_outer, _sb_canvas, ctrl):
            w.bind('<MouseWheel>', _mwheel)

        # Patient info
        self._sec(ctrl, "Patient Information")
        self._lbl(ctrl, "Patient Name:")
        self.pt_name = tk.Entry(ctrl, bg=C_CARD, fg=C_TEXT, relief='flat',
                                 font=FONT_BODY, insertbackground=C_TEXT)
        self.pt_name.pack(fill='x', padx=12, pady=2)

        self._lbl(ctrl, "Patient ID:")
        self.pt_id = tk.Entry(ctrl, bg=C_CARD, fg=C_TEXT, relief='flat',
                               font=FONT_BODY, insertbackground=C_TEXT)
        self.pt_id.pack(fill='x', padx=12, pady=2)

        row_pi = tk.Frame(ctrl, bg=C_PANEL)
        row_pi.pack(fill='x', padx=12, pady=2)
        tk.Label(row_pi, text="Age:", bg=C_PANEL, fg=C_SUBTEXT,
                 font=FONT_SMALL).pack(side='left')
        self.pt_age = tk.Entry(row_pi, bg=C_CARD, fg=C_TEXT, relief='flat',
                                font=FONT_BODY, width=5, insertbackground=C_TEXT)
        self.pt_age.pack(side='left', padx=(4, 12))
        tk.Label(row_pi, text="Sex:", bg=C_PANEL, fg=C_SUBTEXT,
                 font=FONT_SMALL).pack(side='left')
        self.pt_sex = ttk.Combobox(row_pi, values=["M", "F", "Other"],
                                    width=6, state='readonly', font=FONT_BODY)
        self.pt_sex.set("M")
        self.pt_sex.pack(side='left', padx=4)

        self._div(ctrl)
        self._sec(ctrl, "Data Source")
        self._lbl(ctrl, "Heart Rate (bpm):")
        self.var_hr    = tk.DoubleVar(value=75)
        self._spin(ctrl, self.var_hr, 20, 250, 1)
        self._lbl(ctrl, "Duration (s):")
        self.var_dur   = tk.DoubleVar(value=10)
        self._spin(ctrl, self.var_dur, 5, 60, 1)
        noise_row = tk.Frame(ctrl, bg=C_PANEL)
        noise_row.pack(fill='x', padx=12, pady=(4, 0))
        tk.Label(noise_row, text="Noise Level:", bg=C_PANEL, fg=C_SUBTEXT,
                 font=FONT_SMALL).pack(side='left')
        self._noise_val_var = tk.StringVar(value="0.05")
        tk.Label(noise_row, textvariable=self._noise_val_var,
                 bg=C_PANEL, fg=C_ACCENT, font=FONT_SMALL).pack(side='right', padx=4)
        self.var_noise = tk.DoubleVar(value=0.05)
        self.var_noise.trace_add('write',
            lambda *_: self._noise_val_var.set(f"{self.var_noise.get():.2f}"))
        tk.Scale(ctrl, from_=0, to=1, resolution=0.01,
                 variable=self.var_noise, orient='horizontal',
                 bg=C_PANEL, fg=C_TEXT, troughcolor=C_CARD,
                 highlightthickness=0, sliderrelief='flat',
                 activebackground=C_ACCENT, length=230).pack(padx=12, pady=2)
        self._lbl(ctrl, "Sample Rate (Hz):")
        self.var_fs = tk.StringVar(value="500")
        ttk.Combobox(ctrl, textvariable=self.var_fs,
                     values=["250","360","500","1000"],
                     width=12, state='readonly', font=FONT_BODY
                     ).pack(padx=12, pady=2, anchor='w')

        self._lbl(ctrl, "Arrhythmia Mode:")
        self.var_arrh = tk.StringVar(value="None (Normal Sinus)")
        ttk.Combobox(ctrl, textvariable=self.var_arrh,
                     values=["None (Normal Sinus)",
                             "AFib  (Irregular RR)",
                             "PVC  (Premature Beats)",
                             "Missed Beat  (Long Pauses)"],
                     width=24, state='readonly', font=FONT_BODY
                     ).pack(padx=12, pady=2, anchor='w')

        self._btn(ctrl, "Generate Simulated ECG",  self._on_generate,  C_ACCENT)
        self._btn(ctrl, "Load ECG from CSV",        self._on_load_csv,  C_CARD)
        self._btn(ctrl, "Save Sample CSV",          self._on_save_sample, C_CARD)

        self._div(ctrl)
        self._sec(ctrl, "Filter Settings")
        self._lbl(ctrl, "Low cutoff (Hz):")
        self.var_low  = tk.DoubleVar(value=0.5)
        self._spin(ctrl, self.var_low, 0.1, 5.0, 0.1)
        self._lbl(ctrl, "High cutoff (Hz):")
        self.var_high = tk.DoubleVar(value=40)
        self._spin(ctrl, self.var_high, 10, 100, 5)

        self._div(ctrl)
        self._sec(ctrl, "Actions")
        self._btn(ctrl, "STEP 3 — Run Analysis",   self._on_run_analysis, '#238636')
        self._btn(ctrl, "Export PDF Report", self._on_export_pdf, C_CARD)
        self._btn(ctrl, "Export CSV",     self._on_export_csv,   C_CARD)
        self._btn(ctrl, "Reset",          self._on_reset,         C_CARD)

        # Recursively bind mousewheel to every child widget so scrolling
        # works even when the pointer is over a Spinbox or Combobox
        def _recurse_mwheel(w):
            w.bind('<MouseWheel>', _mwheel, add='+')
            for child in w.winfo_children():
                _recurse_mwheel(child)
        self.master.after(200, lambda: _recurse_mwheel(ctrl))

        # ── right: plots + result strip ───────────────────────────────────
        right = tk.Frame(frame, bg=C_BG)
        right.pack(side='right', fill='both', expand=True)

        # Workflow guide banner
        wf = tk.Frame(right, bg=C_CARD, height=30)
        wf.pack(fill='x', padx=6, pady=(6, 0))
        wf.pack_propagate(False)
        tk.Label(wf,
                 text="  STEP 1 — Fill patient info     STEP 2 — Generate or Load ECG     STEP 3 — Run Analysis  ",
                 bg=C_CARD, fg=C_ECG, font=FONT_SMALL,
                 padx=12).pack(side='left', pady=6)
        # right edge accent stripe
        tk.Frame(wf, bg=C_ACCENT, width=3).pack(side='right', fill='y')

        pf = tk.Frame(right, bg=C_BG)
        pf.pack(fill='both', expand=True, padx=6, pady=6)

        self.fig = Figure(figsize=(10, 7), facecolor=C_BG)
        self.fig.subplots_adjust(hspace=0.50, left=0.07, right=0.97, top=0.95, bottom=0.07)
        self.ax_raw  = self.fig.add_subplot(3, 1, 1)
        self.ax_filt = self.fig.add_subplot(3, 1, 2)
        self.ax_hr   = self.fig.add_subplot(3, 1, 3)

        self.canvas = FigureCanvasTkAgg(self.fig, master=pf)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        tb = tk.Frame(pf, bg=C_PANEL)
        tb.pack(fill='x')
        NavigationToolbar2Tk(self.canvas, tb)
        self._init_axes()

        self._build_results_strip(right)

    def _build_results_strip(self, parent):
        strip = tk.Frame(parent, bg=C_PANEL, height=108)
        strip.pack(fill='x', side='bottom', padx=6, pady=(0, 6))
        strip.pack_propagate(False)

        def card(title):
            f = tk.Frame(strip, bg=C_CARD)
            f.pack(side='left', padx=6, pady=8, ipadx=10, ipady=6)
            tk.Label(f, text=title, bg=C_CARD, fg=C_SUBTEXT, font=FONT_SMALL).pack(anchor='w')
            return f

        hr_f = card("HEART RATE")
        self.lbl_hr_val = tk.Label(hr_f, text="-- bpm", bg=C_CARD, fg=C_TEXT, font=FONT_BIG)
        self.lbl_hr_val.pack()

        # ── Cardiac Health Score ──────────────────────────────────────────
        sc_f = tk.Frame(strip, bg=C_CARD)
        sc_f.pack(side='left', padx=6, pady=8, ipadx=14, ipady=6)
        tk.Label(sc_f, text="HEALTH SCORE", bg=C_CARD, fg=C_SUBTEXT,
                 font=FONT_SMALL).pack(anchor='w')
        self.lbl_score_val = tk.Label(sc_f, text="--", bg=C_CARD, fg=C_TEXT,
                                       font=('Segoe UI', 28, 'bold'))
        self.lbl_score_val.pack()
        self.lbl_score_grade = tk.Label(sc_f, text="--", bg=C_CARD, fg=C_SUBTEXT,
                                         font=FONT_SMALL)
        self.lbl_score_grade.pack()

        cls_f = card("CLASSIFICATION")
        self.lbl_cls = tk.Label(cls_f, text="--", bg=C_CARD, fg=C_TEXT,
                                 font=FONT_HEADER, width=30, anchor='w')
        self.lbl_cls.pack()

        q_f = card("SIGNAL QUALITY")
        self.lbl_quality = tk.Label(q_f, text="--", bg=C_CARD, fg=C_TEXT,
                                     font=FONT_BODY, width=32, anchor='w',
                                     wraplength=270, justify='left')
        self.lbl_quality.pack()

        stats_f = tk.Frame(strip, bg=C_CARD)
        stats_f.pack(side='right', padx=6, pady=8, ipadx=10, ipady=6)
        tk.Label(stats_f, text="HRV METRICS", bg=C_CARD, fg=C_SUBTEXT, font=FONT_SMALL).pack(anchor='w')
        self.lbl_stats = tk.Label(stats_f,
            text="SDNN  : --\nRMSSD : --\npNN50 : --",
            bg=C_CARD, fg=C_TEXT, font=FONT_MONO, justify='left')
        self.lbl_stats.pack(anchor='w')

        alert_f = tk.Frame(strip, bg=C_CARD)
        alert_f.pack(side='left', padx=6, pady=8, fill='both', expand=True, ipadx=10, ipady=6)
        tk.Label(alert_f, text="CLINICAL ALERT", bg=C_CARD, fg=C_SUBTEXT, font=FONT_SMALL).pack(anchor='w')
        self.lbl_alert = tk.Label(alert_f, text="No alerts — awaiting analysis",
                                   bg=C_CARD, fg=C_SUBTEXT, font=FONT_HEADER,
                                   anchor='w', justify='left', wraplength=480)
        self.lbl_alert.pack(anchor='w', fill='both', expand=True)

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 2 — LIVE ECG
    # ══════════════════════════════════════════════════════════════════════
    def _build_live_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  ▶  Live ECG  ")

        # left controls
        lc = tk.Frame(frame, bg=C_PANEL, width=240)
        lc.pack(side='left', fill='y')
        lc.pack_propagate(False)

        self._sec(lc, "Live Simulation")
        self._lbl(lc, "Simulated HR (bpm):")
        self.var_live_hr    = tk.DoubleVar(value=72)
        self._spin(lc, self.var_live_hr, 20, 200, 1)
        self._lbl(lc, "Noise Level:")
        self.var_live_noise = tk.DoubleVar(value=0.05)
        tk.Scale(lc, from_=0, to=1, resolution=0.01,
                 variable=self.var_live_noise, orient='horizontal',
                 bg=C_PANEL, fg=C_TEXT, troughcolor=C_CARD,
                 highlightthickness=0, sliderrelief='flat',
                 activebackground=C_ACCENT, length=210).pack(padx=12, pady=2)
        self._lbl(lc, "Display window (s):")
        self.var_live_win = tk.IntVar(value=8)
        self._spin(lc, self.var_live_win, 4, 20, 1)
        self._lbl(lc, "Arrhythmia Mode:")
        self.var_live_arrh = tk.StringVar(value="None (Normal Sinus)")
        ttk.Combobox(lc, textvariable=self.var_live_arrh,
                     values=["None (Normal Sinus)",
                             "AFib  (Irregular RR)",
                             "PVC  (Premature Beats)",
                             "Missed Beat  (Long Pauses)"],
                     width=22, state='readonly', font=FONT_BODY
                     ).pack(padx=12, pady=2, anchor='w')

        self._div(lc)
        self._btn(lc, "START  (Space)", self._live_start, '#238636')
        self._btn(lc, "STOP   (Space)", self._live_stop,  C_RED)

        self._div(lc)
        self._sec(lc, "Live Reading")

        # Beat flash indicator — pulses teal on every R-peak
        beat_row = tk.Frame(lc, bg=C_PANEL)
        beat_row.pack(fill='x', padx=12, pady=(0, 4))
        self._beat_cv = tk.Canvas(beat_row, width=18, height=18,
                                   bg=C_PANEL, highlightthickness=0)
        self._beat_cv.pack(side='left', pady=2)
        self._beat_dot = self._beat_cv.create_oval(2, 2, 16, 16,
                                                    fill=C_PANEL, outline=C_BORDER, width=1)
        tk.Label(beat_row, text=" BEAT", bg=C_PANEL, fg=C_SUBTEXT,
                 font=FONT_SMALL).pack(side='left')
        self._beat_counter_var = tk.StringVar(value="0 beats")
        tk.Label(beat_row, textvariable=self._beat_counter_var,
                 bg=C_PANEL, fg=C_SUBTEXT, font=FONT_SMALL).pack(side='right')
        self._beat_total = 0

        tk.Label(lc, text="HEART RATE", bg=C_PANEL, fg=C_SUBTEXT, font=FONT_SMALL,
                 padx=12).pack(anchor='w')
        self.lbl_live_hr = tk.Label(lc, text="--", bg=C_PANEL, fg=C_ECG, font=FONT_HUGE,
                                     padx=12)
        self.lbl_live_hr.pack(anchor='w')
        tk.Label(lc, text="bpm", bg=C_PANEL, fg=C_SUBTEXT, font=FONT_BODY,
                 padx=12).pack(anchor='w')
        self._div(lc)
        self.lbl_live_cls = tk.Label(lc, text="--", bg=C_PANEL, fg=C_TEXT,
                                      font=FONT_BODY, padx=12, wraplength=200, justify='left')
        self.lbl_live_cls.pack(anchor='w', pady=4)
        self.lbl_live_alert = tk.Label(lc, text="", bg=C_PANEL, fg=C_YELLOW,
                                        font=FONT_SMALL, padx=12, wraplength=200, justify='left')
        self.lbl_live_alert.pack(anchor='w')

        # right: live plot
        rp = tk.Frame(frame, bg=C_BG)
        rp.pack(side='right', fill='both', expand=True)

        self.live_fig = Figure(figsize=(9, 5), facecolor=C_BG)
        self.live_fig.subplots_adjust(left=0.07, right=0.97, top=0.92, bottom=0.10)
        self.live_ax  = self.live_fig.add_subplot(1, 1, 1)
        self._style_ax(self.live_ax, "Live ECG  (scrolling)", "Amplitude (mV)")

        self.live_canvas = FigureCanvasTkAgg(self.live_fig, master=rp)
        self.live_canvas.get_tk_widget().pack(fill='both', expand=True, padx=6, pady=6)
        self.live_line, = self.live_ax.plot([], [], color=C_ECG, linewidth=0.9)
        # Rebuild blit background after any canvas resize.
        # add='+' preserves matplotlib's own <Configure> resize handler so
        # the figure actually grows to fill the widget — without it the
        # figure stays at figsize and the rest of the canvas is white.
        self.live_canvas.get_tk_widget().bind('<Configure>', self._on_live_resize, add='+')

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 3 — MULTI-LEAD
    # ══════════════════════════════════════════════════════════════════════
    def _build_multilead_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  〰  Multi-Lead  ")

        info = tk.Frame(frame, bg=C_PANEL, height=36)
        info.pack(fill='x')
        info.pack_propagate(False)
        tk.Label(info,
                 text="Derived leads (Einthoven):  Lead I  |  Lead II = 1.4×I  |  Lead III = II−I  |  aVF = (II+III)/2  |  aVR = −(I+II)/2",
                 bg=C_PANEL, fg=C_SUBTEXT, font=FONT_SMALL, padx=14).pack(side='left', pady=8)
        self._btn_inline(info, "Refresh Leads", self._plot_multilead)

        pf = tk.Frame(frame, bg=C_BG)
        pf.pack(fill='both', expand=True, padx=6, pady=6)

        self.ml_fig = Figure(figsize=(11, 8), facecolor=C_BG)
        self.ml_fig.subplots_adjust(hspace=0.55, left=0.07, right=0.97, top=0.95, bottom=0.06)
        colours = [C_ECG, '#58a6ff', '#f0883e', '#bc8cff', '#ff7b72']
        names   = ['Lead I', 'Lead II', 'Lead III', 'aVF', 'aVR']
        self.ml_axes = []
        for i, (n, c) in enumerate(zip(names, colours)):
            ax = self.ml_fig.add_subplot(5, 1, i+1)
            self._style_ax(ax, n, 'mV')
            ax.set_xlabel('')
            self.ml_axes.append((ax, c, n))

        self.ml_axes[-1][0].set_xlabel('Time (s)', color=C_SUBTEXT, fontsize=8)

        self.ml_canvas = FigureCanvasTkAgg(self.ml_fig, master=pf)
        self.ml_canvas.get_tk_widget().pack(fill='both', expand=True)

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 4 — CLINICAL ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    def _build_analysis_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  ✚  Clinical Analysis  ")

        self.ca_subtitle_var = tk.StringVar(
            value="Detailed Clinical Analysis  —  run analysis in Monitor tab first")
        tk.Label(frame, textvariable=self.ca_subtitle_var,
                 bg=C_BG, fg=C_SUBTEXT, font=FONT_SMALL, padx=16).pack(anchor='w', pady=(10, 4))

        # split: left = scrollable text report, right = Poincaré plot
        content = tk.Frame(frame, bg=C_BG)
        content.pack(fill='both', expand=True, padx=16, pady=(0, 16))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        # ── left: report text ──────────────────────────────────────────────
        sf = tk.Frame(content, bg=C_BG)
        sf.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        sb = tk.Scrollbar(sf)
        sb.pack(side='right', fill='y')
        self.ca_text = tk.Text(sf, bg=C_CARD, fg=C_TEXT, font=FONT_MONO,
                                relief='flat', padx=12, pady=10,
                                yscrollcommand=sb.set, state='disabled')
        self.ca_text.pack(fill='both', expand=True)
        sb.config(command=self.ca_text.yview)
        self.ca_text.tag_configure('head',  foreground=C_ACCENT, font=('Consolas', 9, 'bold'))
        self.ca_text.tag_configure('ok',    foreground=C_GREEN)
        self.ca_text.tag_configure('warn',  foreground=C_YELLOW)
        self.ca_text.tag_configure('crit',  foreground=C_RED)
        self.ca_text.tag_configure('body',  foreground=C_TEXT)

        # ── right: Poincaré plot ───────────────────────────────────────────
        pc_frame = tk.Frame(content, bg=C_CARD)
        pc_frame.grid(row=0, column=1, sticky='nsew')
        tk.Label(pc_frame, text="POINCARÉ PLOT  (RR(n) vs RR(n+1))",
                 bg=C_CARD, fg=C_ACCENT, font=FONT_SMALL).pack(anchor='w', padx=10, pady=(8, 2))
        self.pc_fig = Figure(figsize=(4, 3.5), facecolor=C_CARD)
        self.pc_fig.subplots_adjust(left=0.16, right=0.96, top=0.90, bottom=0.16)
        self.pc_ax  = self.pc_fig.add_subplot(1, 1, 1)
        self.pc_canvas = FigureCanvasTkAgg(self.pc_fig, master=pc_frame)
        self.pc_canvas.get_tk_widget().pack(fill='both', expand=True, padx=6, pady=(0, 8))
        self._init_poincare()

        self._show_ca_placeholder()

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 5 — HISTORY
    # ══════════════════════════════════════════════════════════════════════
    def _build_history_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  ☰  History  ")

        top = tk.Frame(frame, bg=C_BG)
        top.pack(fill='x', padx=16, pady=(10, 6))
        tk.Label(top, text="Session Analysis History",
                 bg=C_BG, fg=C_TEXT, font=FONT_HEADER).pack(side='left')
        self._btn_inline(top, "Clear History", self._clear_history)
        self._btn_inline(top, "Export History CSV", self._export_history)
        tk.Label(frame,
                 text="Each row is one 'Run Analysis' session.  "
                      "'Export History CSV' saves all rows as a spreadsheet with columns: "
                      "Time, HR (bpm), Classification, Signal Quality, Arrhythmia flag, ST segment, QRS duration.",
                 bg=C_BG, fg=C_SUBTEXT, font=FONT_SMALL,
                 padx=16, wraplength=1200, justify='left').pack(anchor='w', pady=(0, 6))

        cols = ('Time', 'HR (bpm)', 'Classification', 'Quality', 'Arrhythmia', 'ST', 'QRS (ms)')
        s = ttk.Style()
        s.configure('History.Treeview',
                    background=C_CARD, foreground=C_TEXT,
                    fieldbackground=C_CARD, font=FONT_BODY, rowheight=24)
        s.configure('History.Treeview.Heading',
                    background=C_PANEL, foreground=C_ACCENT, font=FONT_SMALL)
        s.map('History.Treeview', background=[('selected', C_ACCENT)])

        self.hist_tree = ttk.Treeview(frame, columns=cols, show='headings',
                                       style='History.Treeview')
        widths = [130, 90, 220, 160, 200, 140, 90]
        for col, w in zip(cols, widths):
            self.hist_tree.heading(col, text=col)
            self.hist_tree.column(col, width=w, minwidth=60)

        sb2 = tk.Scrollbar(frame, command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=sb2.set)
        sb2.pack(side='right', fill='y', padx=(0,6), pady=6)
        self.hist_tree.pack(fill='both', expand=True, padx=6, pady=(0,6))

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 6 — VALIDATION
    # ══════════════════════════════════════════════════════════════════════
    def _build_validation_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  ✓  Validation  ")

        top = tk.Frame(frame, bg=C_BG)
        top.pack(fill='x', padx=18, pady=10)
        tk.Label(top, text="Validation Module — Pre-loaded Test Cases",
                 bg=C_BG, fg=C_TEXT, font=FONT_HEADER).pack(anchor='w')
        tk.Label(top, text="Automatically simulate, filter, analyse and verify expected output for each case.",
                 bg=C_BG, fg=C_SUBTEXT, font=FONT_SMALL).pack(anchor='w', pady=(4, 0))
        tk.Label(top,
                 text="HOW TO USE:  Select a case from the dropdown → click 'Run Selected'  "
                      "(or 'Run All' to test all 6 cases at once).  Each case checks HR accuracy, "
                      "classification, and signal quality against expected values and shows PASS / FAIL.",
                 bg=C_BG, fg=C_SUBTEXT, font=FONT_SMALL,
                 wraplength=900, justify='left').pack(anchor='w', pady=(2, 4))

        sel = tk.Frame(frame, bg=C_CARD)
        sel.pack(fill='x', padx=18, pady=6, ipadx=10, ipady=8)

        tk.Label(sel, text="Case:", bg=C_CARD, fg=C_SUBTEXT,
                 font=FONT_SMALL).grid(row=0, column=0, sticky='w', padx=8, pady=4)
        self.val_var = tk.StringVar(value=list(VALIDATION_CASES.keys())[0])
        ttk.Combobox(sel, textvariable=self.val_var,
                     values=list(VALIDATION_CASES.keys()),
                     width=44, state='readonly', font=FONT_BODY
                     ).grid(row=0, column=1, sticky='w', padx=8, pady=4)
        tk.Button(sel, text=" Run Selected ", command=self._on_run_validation,
                  bg='#238636', fg=C_TEXT, relief='flat', font=FONT_BODY,
                  cursor='hand2', padx=8, pady=3,
                  activebackground='#2ea043', activeforeground=C_TEXT
                  ).grid(row=0, column=2, padx=8, pady=4)
        tk.Button(sel, text=" Run All ", command=self._on_run_all_validations,
                  bg=C_CARD, fg=C_TEXT, relief='flat', font=FONT_BODY,
                  cursor='hand2', padx=8, pady=3,
                  activebackground=C_BORDER, activeforeground=C_TEXT
                  ).grid(row=0, column=3, padx=4, pady=4)

        sf2 = tk.Frame(frame, bg=C_BG)
        sf2.pack(fill='both', expand=True, padx=18, pady=(6, 16))
        sb3 = tk.Scrollbar(sf2)
        sb3.pack(side='right', fill='y')
        self.val_text = tk.Text(sf2, bg=C_CARD, fg=C_TEXT, font=FONT_MONO,
                                 relief='flat', padx=12, pady=10,
                                 yscrollcommand=sb3.set, state='disabled')
        self.val_text.pack(fill='both', expand=True)
        sb3.config(command=self.val_text.yview)
        for tag, fg in [('pass', C_GREEN), ('fail', C_RED),
                        ('warn', C_YELLOW), ('head', C_ACCENT)]:
            self.val_text.tag_configure(tag, foreground=fg)
        self.val_text.tag_configure('head', font=('Consolas', 9, 'bold'))

    # ══════════════════════════════════════════════════════════════════════
    #  TAB 7 — ABOUT
    # ══════════════════════════════════════════════════════════════════════
    def _build_about_tab(self):
        frame = tk.Frame(self.nb, bg=C_BG)
        self.nb.add(frame, text="  ℹ  About  ")
        txt = tk.Text(frame, bg=C_BG, fg=C_TEXT, font=FONT_MONO,
                      relief='flat', padx=28, pady=16, wrap='word')
        txt.insert('1.0', _ABOUT_TEXT)
        txt.configure(state='disabled')
        txt.pack(fill='both', expand=True)

    # ══════════════════════════════════════════════════════════════════════
    #  WIDGET HELPERS
    # ══════════════════════════════════════════════════════════════════════
    def _sec(self, p, t):
        tk.Label(p, text=t.upper(), bg=C_PANEL, fg=C_ACCENT,
                 font=FONT_SMALL, padx=12).pack(anchor='w', pady=(10, 0))
        tk.Frame(p, bg=C_BORDER, height=1).pack(fill='x', padx=12, pady=(2, 6))

    def _lbl(self, p, t):
        tk.Label(p, text=t, bg=C_PANEL, fg=C_SUBTEXT,
                 font=FONT_SMALL, padx=12).pack(anchor='w', pady=(4, 0))

    def _div(self, p):
        tk.Frame(p, bg=C_BORDER, height=1).pack(fill='x', padx=12, pady=8)

    def _spin(self, p, var, lo, hi, inc):
        tk.Spinbox(p, from_=lo, to=hi, increment=inc, textvariable=var,
                   width=10, bg=C_CARD, fg=C_TEXT, relief='flat', font=FONT_BODY,
                   buttonbackground=C_BORDER, insertbackground=C_TEXT
                   ).pack(padx=12, pady=2, anchor='w')

    def _btn(self, p, t, cmd, bg=C_CARD):
        tk.Button(p, text=t, command=cmd, bg=bg, fg=C_TEXT, relief='flat',
                  font=FONT_BODY, cursor='hand2', padx=12, pady=5,
                  activebackground=C_BORDER, activeforeground=C_TEXT
                  ).pack(fill='x', padx=12, pady=3)

    def _btn_inline(self, p, t, cmd, bg=C_CARD):
        tk.Button(p, text=t, command=cmd, bg=bg, fg=C_TEXT, relief='flat',
                  font=FONT_SMALL, cursor='hand2', padx=8, pady=3,
                  activebackground=C_BORDER, activeforeground=C_TEXT
                  ).pack(side='right', padx=6)

    # ══════════════════════════════════════════════════════════════════════
    #  AXES HELPERS
    # ══════════════════════════════════════════════════════════════════════
    def _style_ax(self, ax, title, ylabel):
        ax.set_facecolor(C_BG)
        ax.tick_params(colors=C_SUBTEXT, labelsize=8)
        ax.set_title(title, color=C_TEXT, fontsize=9, pad=4, loc='left')
        ax.set_ylabel(ylabel, color=C_SUBTEXT, fontsize=8)
        ax.set_xlabel("Time (s)", color=C_SUBTEXT, fontsize=8)
        for sp in ax.spines.values(): sp.set_edgecolor(C_BORDER)
        ax.grid(True, color=C_BORDER, linewidth=0.5, linestyle='--', alpha=0.6)

    def _ecg_grid(self, ax, x_min, x_max, y_min, y_max):
        """Overlay standard ECG paper grid (1mm minor, 5mm major)."""
        # 1 small sq = 0.04 s × 0.1 mV;  1 large sq = 0.20 s × 0.5 mV
        for x in np.arange(x_min, x_max, 0.04):
            lw = 0.6 if abs(x % 0.20) < 0.001 else 0.2
            c  = C_GRID_MJ if abs(x % 0.20) < 0.001 else C_GRID_MN
            ax.axvline(x, color=c, linewidth=lw, alpha=0.8, zorder=0)
        for y in np.arange(y_min, y_max, 0.1):
            lw = 0.6 if abs(y % 0.5) < 0.001 else 0.2
            c  = C_GRID_MJ if abs(y % 0.5) < 0.001 else C_GRID_MN
            ax.axhline(y, color=c, linewidth=lw, alpha=0.8, zorder=0)

    def _init_axes(self):
        for ax, t, y in [(self.ax_raw,  "Raw ECG Signal",          "Amplitude (mV)"),
                          (self.ax_filt, "Filtered ECG + R-peaks",  "Amplitude (mV)"),
                          (self.ax_hr,   "Instantaneous Heart Rate", "HR (bpm)")]:
            ax.cla()
            self._style_ax(ax, t, y)
            ax.text(0.5, 0.42, "No data loaded", transform=ax.transAxes,
                    ha='center', va='center', color=C_SUBTEXT, fontsize=9, style='italic')
        self.canvas.draw()

    # ══════════════════════════════════════════════════════════════════════
    #  DATA LOADING
    # ══════════════════════════════════════════════════════════════════════
    def _on_generate(self):
        try:
            hr = float(self.var_hr.get())
            dur= float(self.var_dur.get())
            ns = float(self.var_noise.get())
            fs = int(self.var_fs.get())
            if not (20 <= hr <= 250): raise ValueError("HR must be 20–250 bpm")
            if not (5  <= dur <= 120):raise ValueError("Duration must be 5–120 s")
            # Map dropdown label to internal key
            _arrh_map = {
                "None (Normal Sinus)":      'none',
                "AFib  (Irregular RR)":     'afib',
                "PVC  (Premature Beats)":   'pvc',
                "Missed Beat  (Long Pauses)":'missed',
            }
            arrh = _arrh_map.get(self.var_arrh.get(), 'none')
            self.fs = fs
            self.time_data, self.raw_ecg = ECGProcessor.simulate(dur, fs, hr, ns,
                                                                   arrhythmia=arrh)
            self._plot_raw_only()
            arrh_label = self.var_arrh.get() if arrh != 'none' else "Normal Sinus"
            self._set_status(
                f"Simulated ECG  |  {hr:.0f} bpm  |  {arrh_label}  |  {dur:.0f} s  |  fs={fs} Hz")
        except Exception as e:
            messagebox.showerror("Input Error", str(e))

    def _on_load_csv(self):
        path = filedialog.askopenfilename(
            title="Select ECG CSV",
            filetypes=[("CSV","*.csv"),("All","*.*")])
        if not path: return
        try:
            df = pd.read_csv(path)
            if df.empty: raise ValueError("File is empty")
            col = next((c for c in ['ecg','ECG','amplitude','signal','value']
                        if c in df.columns), None)
            if col is None:
                num = df.select_dtypes(include=[np.number]).columns
                if not len(num): raise ValueError("No numeric column found")
                col = num[0]
            ecg = df[col].dropna().values.astype(float)
            if len(ecg) < 20: raise ValueError("Too few samples")
            fs = int(self.var_fs.get())
            self.fs = fs
            tc = next((c for c in ['time','Time','time_s'] if c in df.columns), None)
            self.time_data = df[tc].values[:len(ecg)].astype(float) if tc else np.arange(len(ecg))/fs
            self.raw_ecg   = ecg
            self._plot_raw_only()
            self._set_status(f"Loaded '{os.path.basename(path)}'  |  {len(ecg)} samples")
        except Exception as e:
            messagebox.showerror("CSV Error", str(e))

    def _on_save_sample(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV","*.csv")], initialfile="sample_ecg.csv")
        if not path: return
        t, ecg = ECGProcessor.simulate(10, 500, 72, 0.05)
        pd.DataFrame({'time_s': t, 'ecg': ecg}).to_csv(path, index=False)
        self._set_status(f"Sample CSV saved: {os.path.basename(path)}")

    # ══════════════════════════════════════════════════════════════════════
    #  ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    def _on_run_analysis(self):
        if self.raw_ecg is None:
            messagebox.showwarning("No Data", "Load or generate ECG data first.")
            return
        threading.Thread(target=self._analysis_worker, daemon=True).start()

    def _analysis_worker(self):
        try:
            self._set_status("Filtering…")
            low, high = float(self.var_low.get()), float(self.var_high.get())
            if low >= high: raise ValueError("Low cutoff must be < high cutoff")
            self.filtered_ecg = ECGProcessor.bandpass(self.raw_ecg, self.fs, low, high)

            self._set_status("Detecting R-peaks…")
            self.r_peaks = ECGProcessor.detect_rpeaks(self.filtered_ecg, self.fs)

            self._set_status("Calculating HR & HRV…")
            self.mean_hr, self.hr_array = ECGProcessor.heart_rate(self.r_peaks, self.fs)

            self._set_status("Running clinical analysis…")
            label, sev   = ECGProcessor.classify(self.mean_hr)
            q_msg, q_ok  = ECGProcessor.signal_quality(self.filtered_ecg)
            arrh         = ECGProcessor.detect_arrhythmia(self.r_peaks, self.fs)
            st           = ECGProcessor.analyze_st(self.filtered_ecg, self.r_peaks, self.fs)
            qrs_d, qrs_m = ECGProcessor.measure_qrs(self.filtered_ecg, self.r_peaks, self.fs)
            hrv          = ECGProcessor.hrv_full(self.r_peaks, self.fs)
            pr_d,  pr_m  = ECGProcessor.measure_pr(self.filtered_ecg, self.r_peaks, self.fs)
            pc           = ECGProcessor.poincare_metrics(self.r_peaks, self.fs)
            hrv_f        = ECGProcessor.hrv_freq(self.r_peaks, self.fs)

            self.last_results = dict(
                timestamp=datetime.now(), label=label, severity=sev,
                mean_hr=self.mean_hr, quality_msg=q_msg, quality_ok=q_ok,
                arrhythmia=arrh, st=st, qrs_dur=qrs_d, qrs_msg=qrs_m, hrv=hrv,
                pr_dur=pr_d, pr_msg=pr_m, poincare=pc, hrv_freq=hrv_f,
                patient=dict(
                    name=self.pt_name.get().strip() or "N/A",
                    id=self.pt_id.get().strip()   or "N/A",
                    age=self.pt_age.get().strip()  or "N/A",
                    sex=self.pt_sex.get()))

            self.master.after(0, self._update_ui,
                              label, sev, q_msg, q_ok, arrh, st, qrs_m, hrv, pr_m, pc, hrv_f)
        except Exception as e:
            self.master.after(0, messagebox.showerror, "Analysis Error", str(e))

    def _update_ui(self, label, sev, q_msg, q_ok, arrh, st, qrs_m, hrv,
                   pr_m=None, pc=None, hrv_f=None):
        self._plot_all()
        self._plot_multilead()

        cm = {'normal': C_GREEN, 'low': C_YELLOW, 'high': C_ORANGE,
              'critical': C_RED, 'error': C_SUBTEXT}
        c  = cm.get(sev, C_TEXT)
        hr_txt = f"{self.mean_hr:.1f} bpm" if self.mean_hr else "-- bpm"
        self.lbl_hr_val.config(text=hr_txt, fg=c)
        self.lbl_cls.config(text=label, fg=c)
        self.lbl_quality.config(text=q_msg, fg=C_GREEN if q_ok else C_YELLOW)

        alert, ac = self._make_alert(sev, q_ok, arrh, st)
        self.lbl_alert.config(text=alert, fg=ac)

        # Cardiac Health Score
        score = ECGProcessor.health_score(sev, hrv, arrh, st)
        grade, gc = ECGProcessor.health_grade(score)
        self.lbl_score_val.config(text=str(score), fg=gc)
        self.lbl_score_grade.config(text=grade, fg=gc)
        self.last_results['health_score'] = score
        self.last_results['health_grade'] = grade

        # HRV strip — include LF/HF when available
        if hrv['sdnn'] is not None:
            lf_hf_str = (f"{hrv_f['lf_hf']:.2f}" if hrv_f and hrv_f.get('lf_hf') else '--')
            self.lbl_stats.config(
                text=f"SDNN  : {hrv['sdnn']:.1f} ms\n"
                     f"RMSSD : {hrv['rmssd']:.1f} ms\n"
                     f"pNN50 : {hrv['pnn50']:.1f} %\n"
                     f"LF/HF : {lf_hf_str}")

        # Poincaré plot in Clinical Analysis tab
        if pc and pc.get('sd1') is not None:
            self._plot_poincare(self.r_peaks, self.fs, pc['sd1'], pc['sd2'])

        # sound alert
        if sev == 'critical' or arrh.get('afib') or st.get('elevation'):
            _beep(critical=True)
        elif sev in ('low', 'high') or arrh.get('irregular') or st.get('depression'):
            _beep(critical=False)

        self._update_analysis_tab(label, sev, q_msg, q_ok, arrh, st, qrs_m, hrv,
                                   pr_m, pc, hrv_f)
        self._add_history(label, sev, q_msg, q_ok, arrh, st, qrs_m)

        # Color-coded status bar
        status_color = {
            'normal': C_GREEN, 'low': C_YELLOW, 'high': C_ORANGE,
            'critical': C_RED, 'error': C_SUBTEXT
        }.get(sev, C_SUBTEXT)
        self._set_status(
            f"Analysis complete  |  {label}  |  Health Score: {score}/100 {grade}  |  {q_msg}",
            color=status_color)

    @staticmethod
    def _make_alert(sev, q_ok, arrh, st):
        lines = []
        if sev == 'critical':
            lines.append("!! CRITICAL — Immediate medical attention !!")
        elif sev == 'low':
            lines.append("WARNING: Bradycardia  (HR < 60 bpm)")
        elif sev == 'high':
            lines.append("WARNING: Tachycardia  (HR > 100 bpm)")
        else:
            lines.append("OK: Normal sinus rhythm")
        if arrh.get('irregular'):
            for m in arrh.get('messages', []): lines.append(m)
        if st.get('elevation'):  lines.append("ST ELEVATION detected — possible MI")
        if st.get('depression'): lines.append("ST Depression detected — possible ischemia")
        if not q_ok:             lines.append("Signal quality issue — check leads")
        colour = C_RED if (sev=='critical' or st.get('elevation')) else (
                 C_YELLOW if (sev in ('low','high') or arrh.get('irregular') or not q_ok)
                 else C_GREEN)
        return "\n".join(lines), colour

    # ══════════════════════════════════════════════════════════════════════
    #  PLOTTING
    # ══════════════════════════════════════════════════════════════════════
    def _plot_raw_only(self):
        self.ax_raw.cla()
        self._style_ax(self.ax_raw, "Raw ECG Signal", "Amplitude (mV)")
        self.ax_raw.plot(self.time_data, self.raw_ecg, color=C_ECG, linewidth=0.8)
        for ax, t, y in [(self.ax_filt, "Filtered ECG + R-peaks", "Amplitude (mV)"),
                          (self.ax_hr,   "Instantaneous Heart Rate", "HR (bpm)")]:
            ax.cla(); self._style_ax(ax, t, y)
            ax.text(0.5, 0.42, "Run Analysis to compute", transform=ax.transAxes,
                    ha='center', va='center', color=C_SUBTEXT, fontsize=9, style='italic')
        self.canvas.draw_idle()

    def _plot_all(self):
        # raw
        self.ax_raw.cla()
        self._style_ax(self.ax_raw, "Raw ECG Signal", "Amplitude (mV)")
        self.ax_raw.plot(self.time_data, self.raw_ecg, color=C_ECG, linewidth=0.7)
        self._ecg_grid(self.ax_raw, self.time_data[0], self.time_data[-1],
                       float(np.min(self.raw_ecg)), float(np.max(self.raw_ecg)))

        # filtered + peaks
        n = len(self.r_peaks) if self.r_peaks is not None else 0
        self.ax_filt.cla()
        self._style_ax(self.ax_filt, f"Filtered ECG  ({n} R-peaks)", "Amplitude (mV)")
        self.ax_filt.plot(self.time_data, self.filtered_ecg, color=C_FILT, linewidth=0.9)
        self._ecg_grid(self.ax_filt, self.time_data[0], self.time_data[-1],
                       float(np.min(self.filtered_ecg)), float(np.max(self.filtered_ecg)))
        if n > 0:
            self.ax_filt.scatter(self.time_data[self.r_peaks],
                                  self.filtered_ecg[self.r_peaks],
                                  color=C_PEAKS, s=45, zorder=5, marker='^', label='R-peaks')
            self.ax_filt.legend(loc='upper right', fontsize=7,
                                 facecolor=C_CARD, edgecolor=C_BORDER, labelcolor=C_TEXT)
            # Annotate P and T waves on the first 3 beats
            for rp in self.r_peaks[:3]:
                for lbl, dt, col in [('P', -0.150, C_YELLOW), ('T', 0.150, '#bc8cff')]:
                    idx = rp + int(dt * self.fs)
                    if 0 <= idx < len(self.filtered_ecg):
                        yv = float(self.filtered_ecg[idx])
                        self.ax_filt.text(
                            self.time_data[idx], yv + 0.08, lbl,
                            color=col, fontsize=7.5, ha='center', va='bottom',
                            fontweight='bold', zorder=6)

        # HR
        self.ax_hr.cla()
        self._style_ax(self.ax_hr, "Instantaneous Heart Rate", "HR (bpm)")
        if len(self.hr_array) >= 1 and n >= 2:
            mt = (self.time_data[self.r_peaks[:-1]] + self.time_data[self.r_peaks[1:]]) / 2
            self.ax_hr.plot(mt, self.hr_array, color=C_ORANGE, linewidth=1.2,
                             marker='o', markersize=4)
            self.ax_hr.axhline(HR_BRADYCARDIA,  color=C_YELLOW, linewidth=0.9,
                                linestyle='--', alpha=0.7, label='60 bpm')
            self.ax_hr.axhline(HR_TACHYCARDIA,  color=C_RED,    linewidth=0.9,
                                linestyle='--', alpha=0.7, label='100 bpm')
            if self.mean_hr:
                self.ax_hr.axhline(self.mean_hr, color=C_ACCENT, linewidth=0.9,
                                    linestyle=':', label=f'Mean {self.mean_hr:.1f}')
            self.ax_hr.legend(loc='upper right', fontsize=7,
                               facecolor=C_CARD, edgecolor=C_BORDER, labelcolor=C_TEXT)
        self.canvas.draw_idle()

    def _plot_multilead(self):
        if self.filtered_ecg is None:
            for ax, colour, name in self.ml_axes:
                ax.cla()
                self._style_ax(ax, name, 'mV')
                ax.set_xlabel('')
                ax.text(0.5, 0.5, "Run Analysis in Monitor tab first",
                        transform=ax.transAxes, ha='center', va='center',
                        color=C_SUBTEXT, fontsize=9, style='italic')
            self.ml_canvas.draw_idle()
            return
        leads = [self.filtered_ecg] + list(ECGProcessor.derive_leads(self.filtered_ecg))
        for (ax, colour, name), sig in zip(self.ml_axes, leads):
            ax.cla()
            self._style_ax(ax, name, 'mV')
            ax.set_xlabel('')
            ax.plot(self.time_data, sig, color=colour, linewidth=0.8)
            self._ecg_grid(ax, self.time_data[0], self.time_data[-1],
                           float(np.min(sig)), float(np.max(sig)))
        self.ml_axes[-1][0].set_xlabel('Time (s)', color=C_SUBTEXT, fontsize=8)
        self.ml_canvas.draw_idle()

    # ══════════════════════════════════════════════════════════════════════
    #  CLINICAL ANALYSIS TAB UPDATE
    # ══════════════════════════════════════════════════════════════════════
    def _show_ca_placeholder(self):
        self.ca_text.configure(state='normal')
        self.ca_text.delete('1.0', 'end')
        self.ca_text.insert('1.0',
            "\n\n  No analysis results yet.\n\n"
            "  HOW TO USE THIS TAB\n"
            "  ──────────────────────────────────────────────────────────\n"
            "  1.  Go to the  Monitor  tab\n"
            "  2.  Fill in patient information (name, ID, age, sex)\n"
            "  3.  Click  'Generate Simulated ECG'  or  'Load ECG from CSV'\n"
            "  4.  Click  'STEP 3 — Run Analysis'\n\n"
            "  The full clinical report will appear here automatically,\n"
            "  including:\n"
            "    •  Heart rate classification\n"
            "    •  HRV metrics  (SDNN, RMSSD, pNN50)\n"
            "    •  Arrhythmia detection  (AFib, PVCs, missed beats)\n"
            "    •  ST-segment analysis  (elevation / depression)\n"
            "    •  QRS duration measurement\n",
            'body')
        self.ca_text.configure(state='disabled')

    def _update_analysis_tab(self, label, sev, q_msg, q_ok, arrh, st, qrs_m, hrv,
                              pr_m=None, pc=None, hrv_f=None):
        r = self.last_results
        pt = r.get('patient', {})
        ts = r['timestamp'].strftime("%Y-%m-%d  %H:%M:%S")

        # Update the subtitle shown above the report text box
        pt_name = pt.get('name') or 'Unknown Patient'
        self.ca_subtitle_var.set(
            f"Clinical Analysis  —  {pt_name}  |  {ts}")

        self.ca_text.configure(state='normal')
        self.ca_text.delete('1.0', 'end')

        def w(txt, tag='body'): self.ca_text.insert('end', txt, tag)

        w("═"*70+"\n", 'head')
        w(f"  CLINICAL ANALYSIS REPORT  —  {ts}\n", 'head')
        w("═"*70+"\n\n", 'head')

        w("  PATIENT\n", 'head')
        w(f"    Name       : {pt.get('name','N/A')}\n")
        w(f"    ID         : {pt.get('id','N/A')}\n")
        w(f"    Age / Sex  : {pt.get('age','N/A')} / {pt.get('sex','N/A')}\n\n")

        w("  HEART RATE\n", 'head')
        c_tag = 'crit' if sev=='critical' else ('warn' if sev in ('low','high') else 'ok')
        w(f"    Result     : {label}\n", c_tag)
        if self.mean_hr:
            w(f"    Mean HR    : {self.mean_hr:.1f} bpm\n")
        w(f"    Signal     : {q_msg}\n", 'ok' if q_ok else 'warn')

        w("\n  HRV METRICS\n", 'head')
        if hrv['sdnn'] is not None:
            w(f"    SDNN       : {hrv['sdnn']:.1f} ms   (normal > 50 ms)\n",
              'ok' if hrv['sdnn'] > 50 else 'warn')
            w(f"    RMSSD      : {hrv['rmssd']:.1f} ms   (short-term variability)\n")
            w(f"    pNN50      : {hrv['pnn50']:.1f} %    (normal > 3%)\n",
              'ok' if hrv['pnn50'] > 3 else 'warn')
        else:
            w("    Insufficient data\n", 'warn')

        w("\n  ARRHYTHMIA ANALYSIS\n", 'head')
        for m in arrh.get('messages', []):
            tag = 'warn' if arrh.get('irregular') else 'ok'
            w(f"    {m}\n", tag)
        w(f"    RR CV      : {arrh.get('cv', 0):.3f}  (AFib threshold > {AFIB_CV_THR})\n")

        w("\n  ST SEGMENT\n", 'head')
        st_tag = 'crit' if st.get('elevation') else ('warn' if st.get('depression') else 'ok')
        w(f"    {st.get('message','N/A')}\n", st_tag)

        w("\n  QRS COMPLEX\n", 'head')
        w(f"    {qrs_m}\n", 'warn' if (self.last_results.get('qrs_dur') or 0) > QRS_WIDE_THR else 'ok')

        if pr_m:
            w("\n  PR INTERVAL\n", 'head')
            pr_dur = r.get('pr_dur') or 0
            pr_tag = 'ok' if 120 <= pr_dur <= 200 else 'warn'
            w(f"    {pr_m}\n", pr_tag)

        if hrv_f and hrv_f.get('lf') is not None:
            w("\n  FREQUENCY-DOMAIN HRV\n", 'head')
            w(f"    LF power  : {hrv_f['lf']:.1f} ms²  (0.04–0.15 Hz — sympathetic)\n")
            w(f"    HF power  : {hrv_f['hf']:.1f} ms²  (0.15–0.40 Hz — parasympathetic)\n")
            lf_hf_s = f"{hrv_f['lf_hf']:.2f}" if hrv_f.get('lf_hf') else '--'
            lf_tag  = 'ok' if (hrv_f.get('lf_hf') or 99) < 2.0 else 'warn'
            w(f"    LF/HF     : {lf_hf_s}  (normal < 2.0; ↑ indicates sympathetic stress)\n", lf_tag)
        elif hrv_f is not None:
            w("\n  FREQUENCY-DOMAIN HRV\n", 'head')
            w("    Insufficient data — need ≥ 20 s recording for reliable spectral analysis\n", 'warn')

        if pc and pc.get('sd1') is not None:
            w("\n  POINCARÉ PLOT METRICS\n", 'head')
            w(f"    SD1 : {pc['sd1']:.1f} ms  (short-term variability — parasympathetic)\n")
            w(f"    SD2 : {pc['sd2']:.1f} ms  (long-term variability  — sympathetic)\n")
            if pc.get('sd_ratio') is not None:
                sr_tag = 'ok' if pc['sd_ratio'] < 1.0 else 'warn'
                w(f"    SD1/SD2 : {pc['sd_ratio']:.3f}  (vagal dominance when < 1.0)\n", sr_tag)

        score = r.get('health_score')
        grade = r.get('health_grade')
        if score is not None:
            score_tag = 'ok' if score >= 60 else ('warn' if score >= 40 else 'crit')
            w("\n  CARDIAC HEALTH SCORE\n", 'head')
            w(f"    Score  : {score} / 100  —  {grade}\n", score_tag)
            w( "    Basis  : HR severity (30) + HRV/SDNN (25) + Arrhythmia (25) + ST (20)\n")

        w("\n"+"═"*70+"\n", 'head')
        self.ca_text.configure(state='disabled')

    # ══════════════════════════════════════════════════════════════════════
    #  HISTORY
    # ══════════════════════════════════════════════════════════════════════
    def _add_history(self, label, sev, q_msg, q_ok, arrh, st, qrs_m):
        ts  = datetime.now().strftime("%H:%M:%S")
        hr  = f"{self.mean_hr:.1f}" if self.mean_hr else "--"
        arr = "Yes" if arrh.get('irregular') else "No"
        st_s= "ELEV" if st.get('elevation') else ("DEPR" if st.get('depression') else "Normal")
        qrs = f"{self.last_results.get('qrs_dur'):.0f}" if self.last_results.get('qrs_dur') else "--"
        row = (ts, hr, label, q_msg, arr, st_s, qrs)
        self.history.append(dict(zip(
            ('time','hr','classification','quality','arrhythmia','st','qrs'), row)))
        self.hist_tree.insert('', 0, values=row)

    def _clear_history(self):
        self.history.clear()
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)

    def _export_history(self):
        if not self.history:
            messagebox.showinfo("History", "No history to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV","*.csv")], initialfile="ecg_history.csv")
        if not path: return
        pd.DataFrame(self.history).to_csv(path, index=False)
        self._set_status(f"History exported: {os.path.basename(path)}")

    # ══════════════════════════════════════════════════════════════════════
    #  LIVE ECG  (blit-accelerated)
    # ══════════════════════════════════════════════════════════════════════
    def _live_start(self):
        if self._live_running: return
        self._live_running     = True
        fs  = self._live_fs
        win = int(self.var_live_win.get())
        self._live_buf         = np.zeros(fs * win)
        self._live_hr_val      = float(self.var_live_hr.get())
        self._live_frame_count = 0
        self._live_beat_count  = 0
        self._live_q           = np.zeros(0)
        self._live_q_pos       = 0
        self._live_r_at        = []
        self._live_ax_setup(win)
        self._live_loop()

    def _live_ax_setup(self, win):
        self.live_ax.cla()
        self._style_ax(self.live_ax, "Live ECG  (scrolling)", "Amplitude (mV)")
        self.live_ax.set_xlim(0, win)
        self.live_ax.set_ylim(-0.5, 1.4)
        # Draw grid once into the static background
        self._ecg_grid(self.live_ax, 0, win, -0.5, 1.4)
        # animated=True excludes this line from the normal draw() pass so
        # copy_from_bbox captures only the grid/axes background
        self.live_line, = self.live_ax.plot([], [], color=C_ECG, linewidth=0.9, animated=True)
        self.live_canvas.draw()
        # Capture the FULL figure (not just axes bbox) so that dark margins
        # and the title area are included in the blit background.
        self._live_bg = self.live_canvas.copy_from_bbox(self.live_fig.bbox)

    def _live_loop(self):
        if not self._live_running: return
        fs    = self._live_fs
        chunk = self._live_chunk
        noise = float(self.var_live_noise.get())

        # Sync HR from slider (new beats will use updated rate)
        self._live_hr_val = float(self.var_live_hr.get())

        # Refill beat queue — keep at least 8× chunk ahead to prevent gaps
        while len(self._live_q) < chunk * 8:
            self._live_enqueue_beat()

        # Dequeue one chunk
        new              = self._live_q[:chunk].copy()
        self._live_q     = self._live_q[chunk:]
        old_pos          = self._live_q_pos
        self._live_q_pos += chunk

        # Flash indicator for every R-peak crossed this chunk
        for r in self._live_r_at:
            if old_pos <= r < self._live_q_pos:
                self.master.after(0, self._flash_beat)
        self._live_r_at = [r for r in self._live_r_at if r >= self._live_q_pos]

        new += noise * np.random.randn(chunk)

        self._live_buf = np.roll(self._live_buf, -chunk)
        self._live_buf[-chunk:] = new

        win   = len(self._live_buf)
        t_arr = np.linspace(0, win / fs, win)
        self.live_line.set_data(t_arr, self._live_buf)

        # Blit: restore full-figure background, redraw animated line, push to screen
        self.live_canvas.restore_region(self._live_bg)
        self.live_ax.draw_artist(self.live_line)
        self.live_canvas.blit(self.live_fig.bbox)
        self.live_canvas.flush_events()

        # Throttle expensive HR computation to every 20 frames (~1 s at 50 ms/frame)
        self._live_frame_count += 1
        if self._live_frame_count % 20 == 0:
            try:
                filt  = ECGProcessor.bandpass(self._live_buf, fs, 0.5, 40)
                peaks = ECGProcessor.detect_rpeaks(filt, fs)
                hr, _ = ECGProcessor.heart_rate(peaks, fs)
                if hr:
                    lbl, sev = ECGProcessor.classify(hr)
                    cm = {'normal':C_GREEN,'low':C_YELLOW,'high':C_ORANGE,
                          'critical':C_RED,'error':C_SUBTEXT}
                    self.lbl_live_hr.config(text=f"{hr:.0f}", fg=cm.get(sev, C_TEXT))
                    self.lbl_live_cls.config(text=lbl)
                    alert, ac = self._make_alert(sev, True,
                        dict(irregular=False, messages=[]),
                        dict(elevation=False, depression=False))
                    self.lbl_live_alert.config(text=alert, fg=ac)
            except Exception:
                pass

        self._live_after_id = self.master.after(50, self._live_loop)

    def _live_stop(self):
        self._live_running = False
        if self._live_after_id:
            self.master.after_cancel(self._live_after_id)
            self._live_after_id = None
        self.lbl_live_hr.config(text="--", fg=C_ECG)
        self.lbl_live_cls.config(text="Stopped")
        self.lbl_live_alert.config(text="")

    def _live_enqueue_beat(self):
        """Generate one arrhythmia-aware beat and append it to the sample queue."""
        self._live_beat_count += 1
        bc   = self._live_beat_count
        _map = {"None (Normal Sinus)":       'none',
                "AFib  (Irregular RR)":      'afib',
                "PVC  (Premature Beats)":    'pvc',
                "Missed Beat  (Long Pauses)":'missed'}
        mode = _map.get(self.var_live_arrh.get(), 'none')
        if mode == 'afib':
            jitter = 1.0 + np.random.uniform(-0.35, 0.35)
        elif mode == 'pvc':
            cyc = bc % 6
            jitter = 0.65 if cyc == 0 else (1.35 if cyc == 1 else
                                             1.0 + np.random.uniform(-0.03, 0.03))
        elif mode == 'missed':
            jitter = 2.0 if bc % 7 == 0 else 1.0 + np.random.uniform(-0.03, 0.03)
        else:
            jitter = 1.0 + np.random.uniform(-0.03, 0.03)
        beat  = ECGProcessor._beat(self._live_fs, self._live_hr_val * max(jitter, 0.3))
        r_abs = self._live_q_pos + len(self._live_q) + int(0.32 * len(beat))
        self._live_r_at.append(r_abs)
        self._live_q = np.concatenate([self._live_q, beat])

    def _on_live_resize(self, event):
        """Rebuild the blit background after the canvas is resized.
        Deferred by one Tk cycle so matplotlib's own resize handler runs first."""
        if self._live_running and self._live_bg is not None:
            self.master.after(50, self._recapture_live_bg)

    def _recapture_live_bg(self):
        if self._live_running:
            self.live_canvas.draw()
            self._live_bg = self.live_canvas.copy_from_bbox(self.live_fig.bbox)

    def _flash_beat(self):
        """Light up the beat indicator dot and increment the beat counter."""
        self._beat_total += 1
        self._beat_counter_var.set(f"{self._beat_total} beats")
        self._beat_cv.itemconfig(self._beat_dot, fill=C_ECG, outline=C_ECG)
        self.master.after(80, self._beat_fade)

    def _beat_fade(self):
        """Dim the beat indicator dot back to idle state."""
        self._beat_cv.itemconfig(self._beat_dot, fill=C_PANEL, outline=C_BORDER)

    # ══════════════════════════════════════════════════════════════════════
    #  VALIDATION
    # ══════════════════════════════════════════════════════════════════════
    def _on_run_validation(self):
        threading.Thread(target=self._val_worker,
                         args=([self.val_var.get()],), daemon=True).start()

    def _on_run_all_validations(self):
        threading.Thread(target=self._val_worker,
                         args=(list(VALIDATION_CASES.keys()),), daemon=True).start()

    def _val_worker(self, names):
        results = []
        for name in names:
            p = VALIDATION_CASES[name]
            t, ecg   = ECGProcessor.simulate(p['duration'], 500, p['hr'], p['noise'])
            filt     = ECGProcessor.bandpass(ecg, 500, 0.5, 40)
            peaks    = ECGProcessor.detect_rpeaks(filt, 500)
            mean_hr, _= ECGProcessor.heart_rate(peaks, 500)
            label, sev= ECGProcessor.classify(mean_hr)
            q_msg, q_ok = ECGProcessor.signal_quality(filt)
            results.append((name, p, mean_hr, label, sev, q_msg, q_ok, len(peaks)))
        self.master.after(0, self._show_validation, results)

    def _show_validation(self, results):
        self.val_text.configure(state='normal')
        self.val_text.delete('1.0', 'end')

        def w(txt, tag=''):
            self.val_text.insert('end', txt, tag)

        all_pass = True
        for name, p, mean_hr, label, sev, q_msg, q_ok, n_peaks in results:
            w("="*66+"\n", 'head')
            w(f"  {name}\n", 'head')
            w("="*66+"\n")
            w(f"  Target HR  : {p['hr']} bpm  |  Noise: {p['noise']}  |  Dur: {p['duration']}s\n")
            w(f"  Detected   : {mean_hr:.1f} bpm\n" if mean_hr else "  Detected   : --\n")
            w(f"  Class      : {label}\n")
            qtag = 'pass' if q_ok else 'warn'
            w(f"  Quality    : {q_msg}\n", qtag)

            hr_pass = mean_hr is not None and abs(mean_hr - p['hr']) < 15
            cls_pass= sev == p['expect'] or (sev=='critical' and p['expect'] in ('low','high'))
            q_pass  = q_ok == p['eq']
            all_pass = all_pass and hr_pass and cls_pass and q_pass

            w(f"  HR check   : {'PASS' if hr_pass  else 'FAIL'}\n", 'pass' if hr_pass  else 'fail')
            w(f"  Class check: {'PASS' if cls_pass else 'FAIL'}\n", 'pass' if cls_pass else 'fail')
            w(f"  Quality chk: {'PASS' if q_pass   else 'FAIL'}\n\n", 'pass' if q_pass  else 'fail')

        w("="*66+"\n", 'head')
        tag = 'pass' if all_pass else 'fail'
        w(f"  OVERALL: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}\n", tag)
        w("="*66+"\n", 'head')
        self.val_text.configure(state='disabled')

    # ══════════════════════════════════════════════════════════════════════
    #  PDF EXPORT
    # ══════════════════════════════════════════════════════════════════════
    def _on_export_pdf(self):
        if not self.last_results:
            messagebox.showwarning("No Results", "Run analysis first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
            filetypes=[("PDF","*.pdf")], initialfile="ecg_report.pdf")
        if not path: return
        try:
            self._generate_pdf(path)
            self._set_status(f"PDF report saved: {os.path.basename(path)}")
            messagebox.showinfo("PDF Saved", f"Report saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("PDF Error", str(e))

    def _generate_pdf(self, path):
        r   = self.last_results
        pt  = r.get('patient', {})
        hrv = r.get('hrv', {})
        st  = r.get('st',  {})
        arr = r.get('arrhythmia', {})
        ts  = r['timestamp'].strftime("%Y-%m-%d  %H:%M:%S")

        with PdfPages(path) as pdf:
            # ── Page 1: Summary ──────────────────────────────────────────
            fig1, ax1 = matplotlib.pyplot.subplots(figsize=(8.27, 11.69))
            ax1.axis('off')
            fig1.patch.set_facecolor('white')
            lines = [
                ("ECG INTELLIGENT MONITORING SOFTWARE", 20, 'bold', '#1a1a2e'),
                ("Clinical Report  —  Group 1", 13, 'normal', '#555555'),
                ("", 11, 'normal', 'white'),
                (f"Date / Time   :  {ts}", 11, 'normal', 'black'),
                (f"Patient Name  :  {pt.get('name','N/A')}", 11, 'normal', 'black'),
                (f"Patient ID    :  {pt.get('id','N/A')}", 11, 'normal', 'black'),
                (f"Age / Sex     :  {pt.get('age','N/A')} / {pt.get('sex','N/A')}", 11, 'normal', 'black'),
                ("", 11, 'normal', 'white'),
                ("─── HEART RATE ─────────────────────────────────────", 11, 'bold', '#2f81f7'),
                (f"Mean HR       :  {r['mean_hr']:.1f} bpm" if r['mean_hr'] else "Mean HR : --", 13, 'bold', 'black'),
                (f"Classification:  {r['label']}", 12, 'bold',
                 '#e74c3c' if r['severity']=='critical' else
                 ('#f39c12' if r['severity'] in ('low','high') else '#27ae60')),
                ("", 11, 'normal', 'white'),
                ("─── SIGNAL QUALITY ─────────────────────────────────", 11, 'bold', '#2f81f7'),
                (r['quality_msg'], 11, 'normal', 'black'),
                ("", 11, 'normal', 'white'),
                ("─── HRV METRICS ────────────────────────────────────", 11, 'bold', '#2f81f7'),
                (f"SDNN  :  {hrv['sdnn']:.1f} ms  (normal > 50 ms)" if hrv.get('sdnn') else "SDNN  :  --", 11, 'normal', 'black'),
                (f"RMSSD :  {hrv['rmssd']:.1f} ms" if hrv.get('rmssd') else "RMSSD :  --", 11, 'normal', 'black'),
                (f"pNN50 :  {hrv['pnn50']:.1f} %  (normal > 3%)" if hrv.get('pnn50') is not None else "pNN50 :  --", 11, 'normal', 'black'),
                ("", 11, 'normal', 'white'),
                ("─── ARRHYTHMIA ─────────────────────────────────────", 11, 'bold', '#2f81f7'),
            ] + [(m, 11, 'normal', '#c0392b' if arr.get('irregular') else 'black')
                 for m in arr.get('messages', [])] + [
                ("", 11, 'normal', 'white'),
                ("─── ST SEGMENT ─────────────────────────────────────", 11, 'bold', '#2f81f7'),
                (st.get('message', 'N/A'), 11, 'normal',
                 '#c0392b' if st.get('elevation') else
                 ('#e67e22' if st.get('depression') else 'black')),
                ("", 11, 'normal', 'white'),
                ("─── QRS COMPLEX ────────────────────────────────────", 11, 'bold', '#2f81f7'),
                (r.get('qrs_msg', 'N/A'), 11, 'normal', 'black'),
            ]
            y = 0.97
            for txt, sz, wt, col in lines:
                ax1.text(0.05, y, txt, transform=ax1.transAxes,
                         fontsize=sz, fontweight=wt, color=col, va='top',
                         fontfamily='monospace' if '──' not in txt else 'sans-serif')
                y -= sz / 380.0
            pdf.savefig(fig1, bbox_inches='tight')
            matplotlib.pyplot.close(fig1)

            # ── Page 2: ECG plots ────────────────────────────────────────
            if self.raw_ecg is not None:
                fig2, axes = matplotlib.pyplot.subplots(3, 1, figsize=(11.69, 8.27))
                fig2.patch.set_facecolor('white')
                fig2.subplots_adjust(hspace=0.50)
                data = [
                    (self.raw_ecg,      'Raw ECG Signal',         '#005500'),
                    (self.filtered_ecg, 'Filtered ECG',           '#000055'),
                ]
                for ax, (sig, ttl, col) in zip(axes[:2], data):
                    ax.plot(self.time_data, sig, color=col, linewidth=0.7)
                    ax.set_title(ttl, fontsize=10)
                    ax.set_xlabel('Time (s)', fontsize=8)
                    ax.set_ylabel('mV', fontsize=8)
                    ax.grid(True, linestyle='--', alpha=0.5, color='#ffcccc')
                    ax.set_facecolor('#fff8f8')
                    for sp in ax.spines.values(): sp.set_edgecolor('#cccccc')
                # HR plot
                ax = axes[2]
                if len(self.hr_array) >= 1 and self.r_peaks is not None and len(self.r_peaks) >= 2:
                    mt = (self.time_data[self.r_peaks[:-1]] + self.time_data[self.r_peaks[1:]]) / 2
                    ax.plot(mt, self.hr_array, color='#883300', linewidth=1.2,
                             marker='o', markersize=3)
                    ax.axhline(60,  color='orange', linewidth=0.8, linestyle='--', label='60 bpm')
                    ax.axhline(100, color='red',    linewidth=0.8, linestyle='--', label='100 bpm')
                    ax.legend(fontsize=7)
                ax.set_title('Instantaneous Heart Rate', fontsize=10)
                ax.set_xlabel('Time (s)', fontsize=8)
                ax.set_ylabel('bpm', fontsize=8)
                ax.grid(True, linestyle='--', alpha=0.5)
                ax.set_facecolor('#fff8f8')
                fig2.suptitle(f"ECG Signal  —  {ts}  —  Patient: {pt.get('name','N/A')}",
                               fontsize=11, y=0.99)
                pdf.savefig(fig2, bbox_inches='tight')
                matplotlib.pyplot.close(fig2)

    # ══════════════════════════════════════════════════════════════════════
    #  CSV EXPORT & RESET
    # ══════════════════════════════════════════════════════════════════════
    def _on_export_csv(self):
        if self.raw_ecg is None:
            messagebox.showwarning("No Data", "Nothing to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV","*.csv")], initialfile="ecg_results.csv")
        if not path: return
        df = pd.DataFrame({'time_s': self.time_data, 'raw_ecg': self.raw_ecg})
        if self.filtered_ecg is not None: df['filtered_ecg'] = self.filtered_ecg
        if self.r_peaks is not None and len(self.r_peaks):
            rp = np.zeros(len(self.raw_ecg), dtype=int)
            rp[self.r_peaks] = 1
            df['r_peak'] = rp
        df.to_csv(path, index=False)
        self._set_status(f"CSV saved: {os.path.basename(path)}")

    def _on_reset(self):
        self.time_data = self.raw_ecg = self.filtered_ecg = None
        self.r_peaks   = None
        self.mean_hr   = None
        self.hr_array  = np.array([])
        self.last_results = {}
        self._init_axes()
        for lbl, txt, fg in [
            (self.lbl_hr_val, "-- bpm", C_TEXT),
            (self.lbl_cls,    "--",     C_TEXT),
            (self.lbl_quality,"--",     C_TEXT),
            (self.lbl_alert,  "No alerts — awaiting analysis", C_SUBTEXT),
            (self.lbl_stats,  "SDNN  : --\nRMSSD : --\npNN50 : --", C_TEXT),
        ]:
            lbl.config(text=txt, fg=fg)
        self.lbl_score_val.config(text="--", fg=C_TEXT)
        self.lbl_score_grade.config(text="--", fg=C_SUBTEXT)
        self.ca_subtitle_var.set(
            "Detailed Clinical Analysis  —  run analysis in Monitor tab first")
        self._show_ca_placeholder()
        self._init_poincare()
        self._beat_total = 0
        self._beat_counter_var.set("0 beats")
        self._beat_cv.itemconfig(self._beat_dot, fill=C_PANEL, outline=C_BORDER)
        self._set_status("Reset — ready.")

    # ══════════════════════════════════════════════════════════════════════
    #  KEYBOARD SHORTCUTS
    # ══════════════════════════════════════════════════════════════════════
    def _bind_shortcuts(self):
        for key in ('<Control-g>', '<Control-G>'):
            self.master.bind(key, lambda e: self._on_generate())
        for key in ('<Control-r>', '<Control-R>'):
            self.master.bind(key, lambda e: self._on_run_analysis())
        for key in ('<Control-e>', '<Control-E>'):
            self.master.bind(key, lambda e: self._on_export_pdf())
        self.master.bind('<space>', self._toggle_live)

    def _toggle_live(self, event=None):
        if self._live_running:
            self._live_stop()
        else:
            self._live_start()

    # ══════════════════════════════════════════════════════════════════════
    #  POINCARÉ PLOT
    # ══════════════════════════════════════════════════════════════════════
    def _init_poincare(self):
        self.pc_ax.cla()
        self.pc_ax.set_facecolor(C_CARD)
        self.pc_ax.set_title("Run analysis to populate", color=C_SUBTEXT, fontsize=8, pad=3)
        self.pc_ax.set_xlabel("RR(n)  ms", color=C_SUBTEXT, fontsize=7)
        self.pc_ax.set_ylabel("RR(n+1)  ms", color=C_SUBTEXT, fontsize=7)
        self.pc_ax.tick_params(colors=C_SUBTEXT, labelsize=7)
        for sp in self.pc_ax.spines.values(): sp.set_edgecolor(C_BORDER)
        self.pc_ax.grid(True, color=C_BORDER, linewidth=0.4, alpha=0.5)
        self.pc_canvas.draw_idle()

    def _plot_poincare(self, r_peaks, fs, sd1, sd2):
        if r_peaks is None or len(r_peaks) < 4:
            self._init_poincare(); return
        rr    = np.diff(r_peaks) / fs * 1000.0
        rr_n  = rr[:-1];  rr_n1 = rr[1:]
        mu    = float(np.mean(rr))

        self.pc_ax.cla()
        self.pc_ax.set_facecolor(C_CARD)
        self.pc_ax.tick_params(colors=C_SUBTEXT, labelsize=7)
        for sp in self.pc_ax.spines.values(): sp.set_edgecolor(C_BORDER)
        self.pc_ax.grid(True, color=C_BORDER, linewidth=0.4, alpha=0.5)
        self.pc_ax.set_xlabel("RR(n)  ms", color=C_SUBTEXT, fontsize=7)
        self.pc_ax.set_ylabel("RR(n+1)  ms", color=C_SUBTEXT, fontsize=7)

        self.pc_ax.scatter(rr_n, rr_n1, s=14, c=C_ECG, alpha=0.75, zorder=3)
        lo = min(rr.min(), rr_n1.min()) * 0.92
        hi = max(rr.max(), rr_n1.max()) * 1.08
        self.pc_ax.plot([lo, hi], [lo, hi], '--', color=C_SUBTEXT, lw=0.8, zorder=1)

        if sd1 and sd2 and sd1 > 0 and sd2 > 0:
            try:
                from matplotlib.patches import Ellipse
                ell = Ellipse((mu, mu), width=2*sd2, height=2*sd1, angle=45,
                              fill=False, edgecolor=C_ACCENT, lw=1.2,
                              linestyle='--', zorder=4)
                self.pc_ax.add_patch(ell)
            except Exception:
                pass

        title = f"SD1={sd1:.1f} ms   SD2={sd2:.1f} ms" if sd1 else "Poincaré Plot"
        self.pc_ax.set_title(title, color=C_TEXT, fontsize=7.5, pad=3)
        self.pc_canvas.draw_idle()

    def _set_status(self, msg, color=None):
        self.status_var.set(msg)
        self.status_lbl.config(fg=color if color else C_SUBTEXT)


# ═══════════════════════════════════════════════════════════════════════════
#  ABOUT TEXT
# ═══════════════════════════════════════════════════════════════════════════
_ABOUT_TEXT = """\
  ♥  CardiBeat  v2.0  —  Intelligent ECG Monitoring
  Biomedical Electronics Final Assignment  |  Group 1
================================================================================

  "CardiBeat" — Cardio (heart) + Beat (heartbeat).
  A real-time ECG monitoring platform built for clinical awareness,
  biomedical education, and signal processing demonstration.

BIOMEDICAL BACKGROUND
--------------------------------------------------------------------------------
  The ECG records the electrical activity of the heart.  Each beat produces:

    P wave      —  Atrial depolarisation
    QRS complex —  Ventricular depolarisation  (R-peak is the tallest spike)
    T wave      —  Ventricular repolarisation

    Heart Rate  =  60 / RR-interval (seconds)

CLINICAL THRESHOLDS
--------------------------------------------------------------------------------
    Critical Bradycardia  :  HR < 40 bpm
    Bradycardia           :  40–60 bpm
    Normal Sinus Rhythm   :  60–100 bpm
    Tachycardia           :  100–150 bpm
    Critical Tachycardia  :  HR > 150 bpm

    ST Elevation  > +0.10 mV  →  possible myocardial infarction (MI)
    ST Depression < −0.05 mV  →  possible ischaemia
    Wide QRS      > 120 ms    →  possible bundle branch block
    RR CV         > 0.15      →  possible atrial fibrillation (AFib)

HRV METRICS
--------------------------------------------------------------------------------
    SDNN   —  std deviation of RR intervals  (overall variability; normal > 50 ms)
    RMSSD  —  root mean square of successive RR differences  (parasympathetic tone)
    pNN50  —  % of consecutive RR differences > 50 ms  (normal > 3 %)

FEATURES  (v2.0)
--------------------------------------------------------------------------------
    ♥  Monitor          :  ECG load / simulate, bandpass filter, R-peak detect,
                           HR classification, HRV strip, clinical alert panel
    ▶  Live ECG         :  Blit-accelerated real-time scrolling trace + live HR
    〰  Multi-Lead       :  Lead I · II · III · aVF · aVR (Einthoven derivation)
    ✚  Clinical Analysis:  Arrhythmia · ST segment · QRS duration · HRV report
    ☰  History          :  Session log with timestamped CSV export
    ✓  Validation       :  6 pre-loaded test cases with PASS / FAIL scoring
       PDF Export       :  2-page clinical report (summary + ECG plots)
       Sound Alerts     :  Windows chime for abnormal / critical events
       ECG Paper Grid   :  Standard 1 mm / 5 mm grid overlay
       Arrhythmia Sim   :  Induce AFib · PVC · Missed Beat in simulation

LIBRARIES
--------------------------------------------------------------------------------
    numpy · pandas · matplotlib · scipy · tkinter

BUILD
--------------------------------------------------------------------------------
    pyinstaller --onefile --windowed --name CardiBeat ecg_monitor.py
================================================================================
"""


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT  —  lazy-import architecture for fast splash appearance
# ═══════════════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.withdraw()   # hide main window until app is fully built
    try: root.iconbitmap(default='')
    except Exception: pass

    splash = SplashScreen(root)

    def _do_imports():
        """Load heavy scientific libraries in a background thread."""
        global np, pd, matplotlib, Figure, FigureCanvasTkAgg, NavigationToolbar2Tk
        global PdfPages, butter, filtfilt, find_peaks, welch

        t0 = time.time()

        root.after(0, lambda: splash.set_status("Loading NumPy…"))
        import numpy as _np;  np = _np

        root.after(0, lambda: splash.set_status("Loading SciPy…"))
        from scipy.signal import butter as _b, filtfilt as _ff, find_peaks as _fp, welch as _w
        butter = _b;  filtfilt = _ff;  find_peaks = _fp;  welch = _w

        root.after(0, lambda: splash.set_status("Loading Matplotlib…"))
        import matplotlib as _mpl
        try: _mpl.use('TkAgg')
        except Exception: pass
        matplotlib = _mpl
        import matplotlib.pyplot                                   # needed by PDF export
        from matplotlib.figure import Figure as _Fig;  Figure = _Fig
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg as _FCA, NavigationToolbar2Tk as _NT)
        FigureCanvasTkAgg = _FCA;  NavigationToolbar2Tk = _NT
        from matplotlib.backends.backend_pdf import PdfPages as _PP;  PdfPages = _PP

        root.after(0, lambda: splash.set_status("Loading Pandas…"))
        import pandas as _pd;  pd = _pd

        # Ensure the splash is visible for at least 2.5 seconds
        elapsed = time.time() - t0
        if elapsed < 2.5:
            time.sleep(2.5 - elapsed)

        root.after(0, lambda: splash.set_status("Launching application…"))
        time.sleep(0.4)
        root.after(0, _launch)

    def _launch():
        ECGMonitorApp(root)
        root.deiconify()
        splash.close()

    threading.Thread(target=_do_imports, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
