"""Generates the design-canvas artboards from real simulator output.

The plot traces in the mockup are actual signals from dpc, not drawn squiggles,
so the visual design is judged against the shapes it will really have to show.
"""

import io
import json

d = json.load(open("_series.json"))

BG = "#0D1014"
PANEL = "#12161B"
RAISED = "#171C22"
BORDER = "#232A33"
GRID = "#1E252E"
TXT = "#E6EAF0"
SEC = "#8A94A3"
MUT = "#5A6472"
TH1 = "#3987e5"
TH2 = "#d95926"
XT = "#199e70"
XC = "#c98500"
ACMD = "#d55181"
ADEL = "#008300"
TAU = "#9085e9"
CRIT = "#d03b3b"

MONO = "&#39;IBM Plex Mono&#39;, monospace"
MONO_ATTR = "IBM Plex Mono, monospace"


def panel(title, right, body, flex="1"):
    return (
        f'<div style="flex: {flex}; display: flex; flex-direction: column; '
        f'background: {PANEL}; border: 1px solid {BORDER}; border-radius: 4px; '
        f'overflow: hidden;">'
        f'<div style="display: flex; align-items: center; justify-content: space-between; '
        f'padding: 7px 10px 6px; border-bottom: 1px solid {BORDER};">'
        f'<span style="font-size: 10px; font-weight: 600; letter-spacing: 0.09em; '
        f'text-transform: uppercase; color: {SEC};">{title}</span>'
        f'<span style="font-family: {MONO}; font-size: 10px; color: {MUT};">{right}</span>'
        f'</div>{body}</div>'
    )


def key(color, label, dash=False):
    da = ' stroke-dasharray="3 2"' if dash else ""
    return (
        f'<span style="display: flex; align-items: center; gap: 5px;">'
        f'<svg width="14" height="8" style="display: block;">'
        f'<line x1="0" y1="4" x2="14" y2="4" stroke="{color}" stroke-width="2"{da}></line>'
        f'</svg>'
        f'<span style="font-size: 10px; color: {SEC};">{label}</span></span>'
    )


def plot(title, right, inner, legend):
    body = (
        f'<div style="padding: 8px 10px 6px;">'
        f'<svg viewBox="0 0 246 74" style="width: 100%; height: 74px; display: block;">'
        f'<g stroke="{GRID}" stroke-width="0.6">'
        f'<line x1="0" y1="18.5" x2="246" y2="18.5"></line>'
        f'<line x1="0" y1="37" x2="246" y2="37"></line>'
        f'<line x1="0" y1="55.5" x2="246" y2="55.5"></line>'
        f'</g>{inner}</svg>'
        f'<div style="display: flex; gap: 12px; padding-top: 6px;">{legend}</div>'
        f'</div>'
    )
    return panel(title, right, body)


angles = plot(
    "Link angles", "deg",
    f'<polyline points="{d["th1"]}" fill="none" stroke="{TH1}" stroke-width="1.6"></polyline>'
    f'<polyline points="{d["th2"]}" fill="none" stroke="{TH2}" stroke-width="1.6"></polyline>',
    key(TH1, "&#952;&#8321;") + key(TH2, "&#952;&#8322;"))

cart = plot(
    "Cart position", "m",
    f'<line x1="0" y1="{d["zero_x"]}" x2="246" y2="{d["zero_x"]}" stroke="{BORDER}" stroke-width="0.8"></line>'
    f'<polyline points="{d["x_true"]}" fill="none" stroke="{XT}" stroke-width="1.6"></polyline>'
    f'<polyline points="{d["x_count"]}" fill="none" stroke="{XC}" stroke-width="1.6" stroke-dasharray="4 3"></polyline>',
    key(XT, "true") + key(XC, "step count", dash=True))

accel = plot(
    "Acceleration", "m/s&#178;",
    f'<line x1="0" y1="{d["amax_y"]}" x2="246" y2="{d["amax_y"]}" stroke="{CRIT}" stroke-width="0.9" stroke-dasharray="4 3"></line>'
    f'<line x1="0" y1="{d["amin_y"]}" x2="246" y2="{d["amin_y"]}" stroke="{CRIT}" stroke-width="0.9" stroke-dasharray="4 3"></line>'
    f'<polyline points="{d["a_cmd"]}" fill="none" stroke="{ACMD}" stroke-width="1.6"></polyline>'
    f'<polyline points="{d["a_del"]}" fill="none" stroke="{ADEL}" stroke-width="1.6"></polyline>',
    key(ACMD, "commanded") + key(ADEL, "delivered") + key(CRIT, "a_max", dash=True))

torque = plot(
    "Motor torque", "mN&#183;m",
    f'<line x1="0" y1="{d["taup_y"]}" x2="246" y2="{d["taup_y"]}" stroke="{CRIT}" stroke-width="0.9" stroke-dasharray="4 3"></line>'
    f'<line x1="0" y1="{d["taum_y"]}" x2="246" y2="{d["taum_y"]}" stroke="{CRIT}" stroke-width="0.9" stroke-dasharray="4 3"></line>'
    f'<polyline points="{d["tau"]}" fill="none" stroke="{TAU}" stroke-width="1.6"></polyline>',
    key(TAU, "&#964; motor") + key(CRIT, "budget &#177;200", dash=True))


def field(label, value, unit="", editable=False):
    box = (f"background: {BG}; border: 1px solid {BORDER};" if editable
           else "background: transparent; border: 1px solid transparent;")
    return (
        f'<div style="display: flex; align-items: center; justify-content: space-between; '
        f'gap: 8px; padding: 2px 0;">'
        f'<span style="font-size: 11px; color: {SEC};">{label}</span>'
        f'<span style="display: flex; align-items: baseline; gap: 4px; {box} '
        f'border-radius: 3px; padding: 2px 6px;">'
        f'<span style="font-family: {MONO}; font-size: 11.5px; color: {TXT};">{value}</span>'
        f'<span style="font-family: {MONO}; font-size: 10px; color: {MUT};">{unit}</span>'
        f'</span></div>'
    )


def section(title, rows, note=""):
    n = (f'<div style="font-size: 10px; color: {MUT}; padding-top: 4px; '
         f'line-height: 1.4;">{note}</div>') if note else ""
    return (
        f'<div style="display: flex; flex-direction: column; gap: 1px;">'
        f'<div style="font-size: 9.5px; font-weight: 600; letter-spacing: 0.11em; '
        f'text-transform: uppercase; color: {MUT}; padding-bottom: 5px;">{title}</div>'
        f'{rows}{n}</div>'
    )


err_mm = (d["final"]["xc"] - d["final"]["x"]) * 1e3

constants = (
    section("Controller &mdash; constant acceleration",
            field("acceleration", "6.000", "m/s&#178;", True)
            + field("hold for", "0.350", "s", True))
    + section("Scenario &mdash; hanging at rest",
              field("&#952;&#8321;", "180.00", "deg")
              + field("&#952;&#8322;", "180.00", "deg")
              + field("x", "0.000", "m")
              + field("duration", "3.00", "s"))
    + section("Drive",
              field("a_max", "6.000", "m/s&#178;", True)
              + field("v_max", "0.350", "m/s", True)
              + field("jerk_max", "120.0", "m/s&#179;", True)
              + field("&#964;_lag", "3.000", "ms", True)
              + field("&#964; budget", "200.0", "mN&#183;m")
              + field("step res", "12.57", "&#181;m")
              + field("slip", "disabled", "", True))
    + section("Plant",
              field("m_cart", "0.300", "kg")
              + field("m_rotor", "1.330", "kg")
              + field("m&#8321; / m&#8322;", "0.075 / 0.045", "kg")
              + field("l&#8321; / l&#8322;", "0.200 / 0.200", "m")
              + field("lc&#8321; / lc&#8322;", "0.120 / 0.100", "m")
              + field("I&#8321;", "3.00e-4", "kg&#183;m&#178;")
              + field("I&#8322;", "1.50e-4", "kg&#183;m&#178;")
              + field("g", "9.810", "m/s&#178;"),
              "Measured quantities. Edit in params.py.")
    + section("Live",
              field("&#952;&#8321; / &#952;&#8322;",
                    f'{d["final"]["th1"]:.1f} / {d["final"]["th2"]:.1f}', "deg")
              + field("cart x", f'{d["final"]["x"]:.4f}', "m")
              + field("step count", f'{d["final"]["xc"]:.4f}', "m")
              + field("counting error", f"{err_mm:+.2f}", "mm")
              + field("peak &#964;", f'{d["final"]["peak_tau"]:.1f}', "mN&#183;m")
              + field("slipped ticks", "0", "of 3000")
              + field("substeps", "2", ""))
)


def sel(label, value):
    return (
        f'<div style="display: flex; align-items: center; gap: 7px; background: {BG}; '
        f'border: 1px solid {BORDER}; border-radius: 3px; padding: 5px 9px;">'
        f'<span style="font-size: 10px; letter-spacing: 0.05em; text-transform: uppercase; '
        f'color: {MUT};">{label}</span>'
        f'<span style="font-size: 12px; color: {TXT};">{value}</span>'
        f'<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="{SEC}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        f'<polyline points="6 9 12 15 18 9"></polyline></svg></div>'
    )


mech_body = (
    f'<div style="flex: 1; position: relative;">'
    f'<svg viewBox="0 0 1060 400" preserveAspectRatio="xMidYMid meet" '
    f'style="width: 100%; height: 100%; display: block;">'
    f'<g stroke="{GRID}" stroke-width="1">'
    f'<line x1="70" y1="120" x2="990" y2="120"></line>'
    f'<line x1="70" y1="200" x2="990" y2="200"></line>'
    f'<line x1="70" y1="280" x2="990" y2="280"></line></g>'
    f'<line x1="70" y1="300" x2="990" y2="300" stroke="#2A323C" stroke-width="3" '
    f'stroke-linecap="round"></line>'
    f'<g stroke="{MUT}" stroke-width="2" stroke-linecap="round">'
    f'<line x1="70" y1="288" x2="70" y2="312"></line>'
    f'<line x1="990" y1="288" x2="990" y2="312"></line></g>'
    f'<polyline points="596,150 604,128 618,112 636,104 656,105 674,114 688,130" '
    f'fill="none" stroke="{TH2}" stroke-width="2" stroke-opacity="0.22" '
    f'stroke-linecap="round"></polyline>'
    f'<rect x="552" y="284" width="72" height="32" rx="4" fill="none" stroke="{XC}" '
    f'stroke-width="1.5" stroke-dasharray="4 3" stroke-opacity="0.65"></rect>'
    f'<rect x="550" y="284" width="72" height="32" rx="4" fill="{RAISED}" '
    f'stroke="#3D4754" stroke-width="1.5"></rect>'
    f'<line x1="586" y1="300" x2="656" y2="150" stroke="{TH1}" stroke-width="7" '
    f'stroke-linecap="round"></line>'
    f'<line x1="656" y1="150" x2="688" y2="130" stroke="{TH2}" stroke-width="7" '
    f'stroke-linecap="round"></line>'
    f'<circle cx="586" cy="300" r="5.5" fill="{BG}" stroke="{TH1}" stroke-width="2.5"></circle>'
    f'<circle cx="656" cy="150" r="5.5" fill="{BG}" stroke="{TH2}" stroke-width="2.5"></circle>'
    f'<circle cx="688" cy="130" r="4" fill="{TH2}"></circle>'
    f'<text x="86" y="46" font-family="{MONO_ATTR}" font-size="15" fill="{TXT}">'
    f'&#952;&#8321; 174.3&#176;</text>'
    f'<text x="86" y="70" font-family="{MONO_ATTR}" font-size="15" fill="{TXT}">'
    f'&#952;&#8322; 155.6&#176;</text>'
    f'<text x="86" y="94" font-family="{MONO_ATTR}" font-size="15" fill="{SEC}">'
    f'x 0.612 m</text>'
    f'</svg></div>'
)

transport = (
    f'<div style="display: flex; align-items: center; gap: 12px; background: {PANEL}; '
    f'border: 1px solid {BORDER}; border-radius: 4px; padding: 8px 12px;">'
    f'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="{TXT}" '
    f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    f'<rect x="6" y="4" width="4" height="16"></rect>'
    f'<rect x="14" y="4" width="4" height="16"></rect></svg>'
    f'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="{SEC}" '
    f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    f'<polyline points="11 19 2 12 11 5"></polyline>'
    f'<line x1="21" y1="5" x2="21" y2="19"></line></svg>'
    f'<div style="flex-grow: 1; position: relative; height: 4px; background: {BORDER}; '
    f'border-radius: 2px;">'
    f'<div style="position: absolute; left: 0; top: 0; height: 4px; width: 61%; '
    f'background: {TH1}; border-radius: 2px;"></div>'
    f'<div style="position: absolute; left: 61%; top: -4px; width: 3px; height: 12px; '
    f'background: {TXT}; border-radius: 1px;"></div></div>'
    f'<span style="font-family: {MONO}; font-size: 11.5px; color: {TXT};">1.840</span>'
    f'<span style="font-family: {MONO}; font-size: 11.5px; color: {MUT};">/ 3.000 s</span>'
    f'<div style="display: flex; gap: 3px;">'
    f'<span style="font-family: {MONO}; font-size: 10.5px; color: {MUT}; background: {BG}; '
    f'border: 1px solid {BORDER}; border-radius: 3px; padding: 2px 7px;">0.25&#215;</span>'
    f'<span style="font-family: {MONO}; font-size: 10.5px; color: {BG}; background: {TH1}; '
    f'border: 1px solid {TH1}; border-radius: 3px; padding: 2px 7px;">1&#215;</span>'
    f'<span style="font-family: {MONO}; font-size: 10.5px; color: {MUT}; background: {BG}; '
    f'border: 1px solid {BORDER}; border-radius: 3px; padding: 2px 7px;">2&#215;</span>'
    f'</div></div>'
)

HEAD = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&amp;family=IBM+Plex+Mono:wght@400;500&amp;display=swap">
  <style>
    body { margin: 0; font-family: 'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif; }
    a { color: %s; } a:hover { color: #6fb4ee; }
  </style>
</helmet>
""" % TH1

main = (
    HEAD
    + f'<div style="width: 1440px; height: 900px; display: flex; background: {BG}; '
      f'color: {TXT}; font-family: &#39;IBM Plex Sans&#39;, ui-sans-serif, system-ui, sans-serif;">'
    + f'<div style="flex: 1; display: flex; flex-direction: column; gap: 12px; '
      f'padding: 16px; min-width: 0;">'
    + f'<div style="display: flex; align-items: center; gap: 10px;">'
      f'<span style="font-size: 13px; font-weight: 600; letter-spacing: 0.02em; '
      f'color: {TXT};">Double pendulum on a cart</span>'
      f'<span style="flex-grow: 1;"></span>'
    + sel("Controller", "Constant acceleration")
    + sel("Scenario", "Hanging at rest")
    + f'<div style="display: flex; align-items: center; gap: 6px; background: {TH1}; '
      f'border-radius: 3px; padding: 6px 14px;">'
      f'<svg width="10" height="10" viewBox="0 0 24 24" fill="{BG}">'
      f'<polygon points="6 4 20 12 6 20"></polygon></svg>'
      f'<span style="font-size: 12px; font-weight: 600; color: {BG};">Run</span></div></div>'
    + panel("Mechanism", "t = 1.840 s &#183; 1&#215;", mech_body, flex="1.15")
    + transport
    + f'<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); '
      f'gap: 12px;">{angles}{cart}{accel}{torque}</div>'
    + '</div>'
    + f'<div style="width: 300px; display: flex; flex-direction: column; gap: 18px; '
      f'background: {PANEL}; border-left: 1px solid {BORDER}; padding: 16px 16px 20px; '
      f'overflow: hidden;">{constants}</div>'
    + '</div>\n</x-dc>\n</body>\n</html>\n'
)

io.open("Main.dc.html", "w", encoding="utf-8", newline="\n").write(main)
print("Main.dc.html written:", len(main), "bytes")
