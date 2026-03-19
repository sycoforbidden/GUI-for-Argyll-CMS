"""
Color conversion utilities for display purposes.
Converts CMYK device values, Lab, and XYZ to sRGB for on-screen preview.
"""

import math


def cmyk_to_rgb(c, m, y, k):
    """Convert CMYK (0-100 range) to RGB (0-255).
    Simple subtractive model - approximate but sufficient for visual preview.
    """
    c, m, y, k = c / 100.0, m / 100.0, y / 100.0, k / 100.0
    r = int(255 * (1 - c) * (1 - k))
    g = int(255 * (1 - m) * (1 - k))
    b = int(255 * (1 - y) * (1 - k))
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def xyz_to_lab(X, Y, Z):
    """Convert CIE XYZ (scaled 0-100) to CIE L*a*b* (D50 illuminant)."""
    # D50 reference white
    Xn, Yn, Zn = 96.422, 100.0, 82.521

    def f(t):
        if t > 0.008856:
            return t ** (1 / 3)
        return 7.787 * t + 16 / 116

    fx = f(X / Xn)
    fy = f(Y / Yn)
    fz = f(Z / Zn)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return (L, a, b)


def lab_to_xyz(L, a, b):
    """Convert CIE L*a*b* to CIE XYZ (D50 illuminant)."""
    Xn, Yn, Zn = 96.422, 100.0, 82.521

    fy = (L + 16) / 116
    fx = a / 500 + fy
    fz = fy - b / 200

    def finv(t):
        if t > 0.206893:
            return t ** 3
        return (t - 16 / 116) / 7.787

    X = Xn * finv(fx)
    Y = Yn * finv(fy)
    Z = Zn * finv(fz)
    return (X, Y, Z)


def xyz_to_srgb(X, Y, Z):
    """Convert CIE XYZ (D50) to sRGB (0-255).
    Uses Bradford chromatic adaptation from D50 to D65, then XYZ to sRGB matrix.
    """
    # Bradford adaptation D50 -> D65
    M = [
        [0.9555766, -0.0230393, 0.0631636],
        [-0.0282895, 1.0099416, 0.0210077],
        [0.0122982, -0.0204830, 1.3299098],
    ]
    x = X / 100.0
    y = Y / 100.0
    z = Z / 100.0

    # Apply Bradford
    xd = M[0][0] * x + M[0][1] * y + M[0][2] * z
    yd = M[1][0] * x + M[1][1] * y + M[1][2] * z
    zd = M[2][0] * x + M[2][1] * y + M[2][2] * z

    # XYZ (D65) to linear sRGB
    rl = 3.2404542 * xd - 1.5371385 * yd - 0.4985314 * zd
    gl = -0.9692660 * xd + 1.8760108 * yd + 0.0415560 * zd
    bl = 0.0556434 * xd - 0.2040259 * yd + 1.0572252 * zd

    def gamma(u):
        if u <= 0.0031308:
            return 12.92 * u
        return 1.055 * (u ** (1 / 2.4)) - 0.055

    r = int(max(0, min(255, round(gamma(max(0, rl)) * 255))))
    g = int(max(0, min(255, round(gamma(max(0, gl)) * 255))))
    b = int(max(0, min(255, round(gamma(max(0, bl)) * 255))))
    return (r, g, b)


def lab_to_rgb(L, a, b):
    """Convert CIE L*a*b* (D50) to sRGB (0-255)."""
    X, Y, Z = lab_to_xyz(L, a, b)
    return xyz_to_srgb(X, Y, Z)


def xyz_to_rgb(X, Y, Z):
    """Convert CIE XYZ (D50) to sRGB (0-255)."""
    return xyz_to_srgb(X, Y, Z)


def delta_e_76(lab1, lab2):
    """CIE76 Delta E between two L*a*b* colors."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2)))


def delta_e_94(lab1, lab2):
    """CIE94 Delta E (graphic arts) between two L*a*b* colors."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    dL = L1 - L2
    C1 = math.sqrt(a1 ** 2 + b1 ** 2)
    C2 = math.sqrt(a2 ** 2 + b2 ** 2)
    dC = C1 - C2
    da = a1 - a2
    db = b1 - b2
    dH_sq = da ** 2 + db ** 2 - dC ** 2
    dH_sq = max(0, dH_sq)

    SL = 1.0
    SC = 1.0 + 0.045 * C1
    SH = 1.0 + 0.015 * C1

    term1 = (dL / SL) ** 2
    term2 = (dC / SC) ** 2
    term3 = dH_sq / (SH ** 2)

    return math.sqrt(max(0, term1 + term2 + term3))


def rgb_to_hex(r, g, b):
    """Convert RGB tuple to hex color string."""
    return f'#{r:02x}{g:02x}{b:02x}'


def device_color_to_rgb(device_values, color_space='CMYK'):
    """Convert device values to approximate RGB for display.
    device_values: list of floats (0-100 range)
    color_space: 'CMYK', 'RGB', 'CMY'
    """
    if color_space.upper() == 'CMYK' and len(device_values) >= 4:
        return cmyk_to_rgb(*device_values[:4])
    elif color_space.upper() == 'RGB' and len(device_values) >= 3:
        return tuple(int(v * 255 / 100) for v in device_values[:3])
    elif color_space.upper() == 'CMY' and len(device_values) >= 3:
        return cmyk_to_rgb(device_values[0], device_values[1], device_values[2], 0)
    return (128, 128, 128)  # fallback gray
