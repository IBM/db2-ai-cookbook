"""Render the Bedrock -> Db2 workflow as a LinkedIn-optimized PNG.

Mirrors what embed_image.py actually does: read an image, get its embedding
from AWS Bedrock (Titan Multimodal), and store the image + the embedding in
IBM Db2. No similarity search happens in the script, so the diagram stops at
"stored in Db2". Written for people new to image embeddings.

Design choices follow common practice for technical posts on LinkedIn:
a short kicker, a bold mobile-legible title, three numbered steps with
plain-language arrows, and a single highlighted takeaway.

Standalone (matplotlib only). Output: 2400x1350 px (16:9).

    python3 docs/make_workflow_image.py     # -> docs/workflow_linkedin.png
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Polygon, Ellipse, Rectangle

# ---- palette ----------------------------------------------------------------
INK = "#0f1f2e"        # near-black slate for headings/body
SUB = "#5a6b7b"        # muted subtitle
CANVAS = "#f5f8fc"     # page background
CARD = "#ffffff"
EDGE = "#dbe3ec"
ARROW = "#7c8b9a"      # muted slate for arrows
CALLOUT = "#eef3fb"    # takeaway background
IMG_C = "#1f9e8f"      # teal   (input image)
AWS_C = "#ff9900"      # AWS orange
DB2_C = "#0f62fe"      # IBM Carbon blue

W, H = 12.0, 6.75      # inches; at dpi=200 -> 2400x1350 px (16:9)
fig = plt.figure(figsize=(W, H), dpi=200)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")
fig.patch.set_facecolor(CANVAS)
ax.add_patch(Rectangle((0, 0), W, H, color=CANVAS, zorder=0))

# ---- header: kicker + title + subtitle --------------------------------------
ax.text(W / 2, 6.46, "I M A G E   E M B E D D I N G S ,   E X P L A I N E D   S I M P L Y",
        ha="center", va="center", fontsize=11, fontweight="bold", color=AWS_C, zorder=5)
ax.text(W / 2, 5.98, "Turn an Image into a Vector and Store It in IBM Db2",
        ha="center", va="center", fontsize=25, fontweight="bold", color=INK)
ax.text(W / 2, 5.42, "Three steps: take an image, turn it into numbers with AWS Bedrock, and save both in Db2.",
        ha="center", va="center", fontsize=13.5, color=SUB)

# ---- card layout (3 cards) --------------------------------------------------
CARD_W, CARD_H = 2.95, 2.45
CY = 2.55                       # bottom y of cards
GAP = (W - 1.0 - 3 * CARD_W) / 2.0
XS = [0.5 + i * (CARD_W + GAP) for i in range(3)]
CENTERS = [x + CARD_W / 2 for x in XS]
ICON_CY = CY + CARD_H - 0.78
TITLE_Y = CY + 0.90
SUB1_Y = CY + 0.54
SUB2_Y = CY + 0.26


def card(x, accent, step):
    ax.add_patch(FancyBboxPatch((x, CY), CARD_W, CARD_H,
                 boxstyle="round,pad=0.02,rounding_size=0.16",
                 linewidth=1.4, edgecolor=EDGE, facecolor=CARD, zorder=2))
    ax.add_patch(FancyBboxPatch((x + 0.24, CY + CARD_H - 0.12), CARD_W - 0.48, 0.07,
                 boxstyle="round,pad=0.01,rounding_size=0.03",
                 linewidth=0, facecolor=accent, zorder=3))
    bx, by = x + 0.42, CY + CARD_H - 0.40
    ax.add_patch(Circle((bx, by), 0.22, facecolor=accent, edgecolor="white",
                        linewidth=2.0, zorder=6))
    ax.text(bx, by, str(step), ha="center", va="center", fontsize=13,
            fontweight="bold", color="white", zorder=7)


def chip(cx, color):
    ax.add_patch(Circle((cx, ICON_CY), 0.46, facecolor=color, edgecolor="none",
                        alpha=0.15, zorder=3))


def label(cx, title, s1, s2, color):
    ax.text(cx, TITLE_Y, title, ha="center", va="center", fontsize=16.5,
            fontweight="bold", color=INK, zorder=4)
    ax.text(cx, SUB1_Y, s1, ha="center", va="center", fontsize=11.5, color=SUB, zorder=4)
    ax.text(cx, SUB2_Y, s2, ha="center", va="center", fontsize=11.5, color=color,
            fontweight="bold", zorder=4)


# ---- icons (hand-drawn, emoji-free for font portability) --------------------
def icon_image(cx):
    chip(cx, IMG_C)
    ax.add_patch(FancyBboxPatch((cx - 0.32, ICON_CY - 0.25), 0.64, 0.49,
                 boxstyle="round,pad=0.0,rounding_size=0.04",
                 linewidth=2.2, edgecolor=IMG_C, facecolor="white", zorder=4))
    ax.add_patch(Circle((cx + 0.13, ICON_CY + 0.08), 0.055, color=IMG_C, zorder=5))
    ax.add_patch(Polygon([[cx - 0.29, ICON_CY - 0.22], [cx - 0.07, ICON_CY + 0.03],
                          [cx + 0.11, ICON_CY - 0.10], [cx + 0.29, ICON_CY - 0.22]],
                         closed=True, color=IMG_C, zorder=5))


def icon_cloud(cx):
    chip(cx, AWS_C)
    y = ICON_CY - 0.05
    for dx, dy, r in [(-0.22, -0.02, 0.17), (0.0, 0.11, 0.23), (0.24, -0.02, 0.18)]:
        ax.add_patch(Circle((cx + dx, y + dy), r, color=AWS_C, zorder=4))
    ax.add_patch(FancyBboxPatch((cx - 0.37, y - 0.19), 0.74, 0.23,
                 boxstyle="round,pad=0.0,rounding_size=0.10",
                 linewidth=0, facecolor=AWS_C, zorder=4))


def icon_db(cx):
    chip(cx, DB2_C)
    w, top, bot = 0.62, ICON_CY + 0.28, ICON_CY - 0.28
    ax.add_patch(Rectangle((cx - w / 2, bot), w, top - bot, facecolor=DB2_C,
                           edgecolor="none", zorder=4))
    for yy in (top, ICON_CY, bot):
        ax.add_patch(Ellipse((cx, yy), w, 0.21, facecolor="white", edgecolor=DB2_C,
                             linewidth=2.2, zorder=5))
    ax.add_patch(Ellipse((cx, top), w, 0.21, facecolor=DB2_C, edgecolor=DB2_C,
                         linewidth=2.2, zorder=6))


# ---- build cards ------------------------------------------------------------
specs = [
    (icon_image, "An image", "a JPEG or PNG file", "what you start with", IMG_C),
    (icon_cloud, "AWS Bedrock", "the Titan AI model", "reads image → numbers", AWS_C),
    (icon_db, "IBM Db2", "one row stores both", "image + its vector", DB2_C),
]
for x, c, (draw, t, s1, s2, col), step in zip(XS, CENTERS, specs, (1, 2, 3)):
    card(x, col, step)
    draw(c)
    label(c, t, s1, s2, col)

# ---- arrows + plain-language labels -----------------------------------------
edge_labels = [
    ("REST API call", "(sends the image)"),
    ("get the embedding", "store it in Db2"),
]
for i in range(2):
    x0 = XS[i] + CARD_W + 0.06
    x1 = XS[i + 1] - 0.06
    ya = CY + CARD_H / 2
    ax.add_patch(FancyArrowPatch((x0, ya), (x1, ya), arrowstyle="-|>",
                 mutation_scale=26, linewidth=3.0, color=ARROW, zorder=1))
    top, bottom = edge_labels[i]
    ax.text((x0 + x1) / 2, ya + 0.40, top, ha="center", va="center",
            fontsize=11.5, color=INK, fontweight="bold", zorder=5)
    ax.text((x0 + x1) / 2, ya + 0.14, bottom, ha="center", va="center",
            fontsize=10, color=SUB, style="italic", zorder=5)

# ---- takeaway callout -------------------------------------------------------
cx0, cx1, cyb, cyt = 1.25, 10.75, 1.05, 1.95
ax.add_patch(FancyBboxPatch((cx0, cyb), cx1 - cx0, cyt - cyb,
             boxstyle="round,pad=0.02,rounding_size=0.10",
             linewidth=0, facecolor=CALLOUT, zorder=1))
ax.add_patch(Rectangle((cx0 + 0.02, cyb + 0.04), 0.07, cyt - cyb - 0.08, color=DB2_C, zorder=2))
ax.text((cx0 + cx1) / 2, (cyb + cyt) / 2 + 0.02,
        "An embedding is a list of numbers that captures what's in an image —",
        ha="center", va="center", fontsize=12.5, color=INK, zorder=3)
ax.text((cx0 + cx1) / 2, (cyb + cyt) / 2 - 0.26,
        "similar pictures get similar numbers.",
        ha="center", va="center", fontsize=12.5, color=INK, fontweight="bold", zorder=3)

# ---- footer -----------------------------------------------------------------
ax.text(W / 2, 0.58, "github.com/IBM/db2-multimodal-embedding", ha="center", va="center",
        fontsize=11.5, color=DB2_C, fontweight="bold")

out = "docs/workflow_linkedin.png"
fig.savefig(out, dpi=200, facecolor=CANVAS)
print("wrote", out)
