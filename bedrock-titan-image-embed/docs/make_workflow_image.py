"""Render the Bedrock -> Db2 workflow as a LinkedIn-optimized PNG.

Standalone (no module deps): uses matplotlib only. Produces a 16:9 landscape
image at retina resolution (2400x1350) that reads well in the LinkedIn feed.

    python3 docs/make_workflow_image.py
    # -> docs/workflow_linkedin.png
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Polygon, Ellipse, Rectangle

# ---- palette ----------------------------------------------------------------
INK = "#10202e"        # near-black slate for text
SUB = "#5a6b7b"        # muted subtitle
CANVAS = "#f4f7fb"     # page background
CARD = "#ffffff"
EDGE = "#dbe3ec"
ARROW = "#94a3b4"
IMG_C = "#1f9e8f"      # teal  (image)
AWS_C = "#ff9900"      # AWS orange
DB2_C = "#0f62fe"      # IBM Carbon blue
OUT_C = "#24a148"      # IBM Carbon green

W, H = 12.0, 6.75      # inches; at dpi=200 -> 2400x1350 px (16:9)
fig = plt.figure(figsize=(W, H), dpi=200)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")
fig.patch.set_facecolor(CANVAS)
ax.add_patch(Rectangle((0, 0), W, H, color=CANVAS, zorder=0))

# ---- header -----------------------------------------------------------------
ax.text(W / 2, 6.18, "Multimodal Image Search with AWS Bedrock + IBM Db2",
        ha="center", va="center", fontsize=23, fontweight="bold", color=INK)
ax.text(W / 2, 5.62, "Embed an image, store it next to its vector, search with one line of SQL.",
        ha="center", va="center", fontsize=13.5, color=SUB)

# ---- card layout ------------------------------------------------------------
CARD_W, CARD_H = 2.42, 2.55
CY = 2.55                      # bottom y of cards
GAP = (W - 1.0 - 4 * CARD_W) / 3.0
XS = [0.5 + i * (CARD_W + GAP) for i in range(4)]
CENTERS = [x + CARD_W / 2 for x in XS]
ICON_CY = CY + CARD_H - 0.72   # icon center y
TITLE_Y = CY + 0.92
SUB1_Y = CY + 0.56
SUB2_Y = CY + 0.28


def card(x, accent):
    ax.add_patch(FancyBboxPatch((x, CY), CARD_W, CARD_H,
                 boxstyle="round,pad=0.02,rounding_size=0.16",
                 linewidth=1.4, edgecolor=EDGE, facecolor=CARD, zorder=2))
    # accent bar at top of the card
    ax.add_patch(FancyBboxPatch((x + 0.22, CY + CARD_H - 0.12), CARD_W - 0.44, 0.07,
                 boxstyle="round,pad=0.01,rounding_size=0.03",
                 linewidth=0, facecolor=accent, zorder=3))


def chip(cx, color):
    ax.add_patch(Circle((cx, ICON_CY), 0.42, facecolor=color, edgecolor="none",
                        alpha=0.16, zorder=3))


def label(cx, title, s1, s2, color):
    ax.text(cx, TITLE_Y, title, ha="center", va="center", fontsize=14.5,
            fontweight="bold", color=INK, zorder=4)
    ax.text(cx, SUB1_Y, s1, ha="center", va="center", fontsize=11, color=SUB, zorder=4)
    ax.text(cx, SUB2_Y, s2, ha="center", va="center", fontsize=11, color=color,
            fontweight="bold", zorder=4)


# ---- icons (hand-drawn, emoji-free for font portability) --------------------
def icon_image(cx):
    chip(cx, IMG_C)
    ax.add_patch(FancyBboxPatch((cx - 0.30, ICON_CY - 0.24), 0.60, 0.46,
                 boxstyle="round,pad=0.0,rounding_size=0.04",
                 linewidth=2.0, edgecolor=IMG_C, facecolor="white", zorder=4))
    ax.add_patch(Circle((cx + 0.12, ICON_CY + 0.07), 0.05, color=IMG_C, zorder=5))
    ax.add_patch(Polygon([[cx - 0.27, ICON_CY - 0.21], [cx - 0.07, ICON_CY + 0.02],
                          [cx + 0.10, ICON_CY - 0.10], [cx + 0.27, ICON_CY - 0.21]],
                         closed=True, color=IMG_C, zorder=5))


def icon_cloud(cx):
    chip(cx, AWS_C)
    y = ICON_CY - 0.05
    for dx, dy, r in [(-0.20, -0.02, 0.16), (0.0, 0.10, 0.21), (0.22, -0.02, 0.17)]:
        ax.add_patch(Circle((cx + dx, y + dy), r, color=AWS_C, zorder=4))
    ax.add_patch(FancyBboxPatch((cx - 0.34, y - 0.18), 0.68, 0.22,
                 boxstyle="round,pad=0.0,rounding_size=0.10",
                 linewidth=0, facecolor=AWS_C, zorder=4))


def icon_db(cx):
    chip(cx, DB2_C)
    w, top, bot = 0.58, ICON_CY + 0.26, ICON_CY - 0.26
    ax.add_patch(Rectangle((cx - w / 2, bot), w, top - bot, facecolor=DB2_C,
                           edgecolor="none", zorder=4))
    for yy in (top, ICON_CY, bot):
        ax.add_patch(Ellipse((cx, yy), w, 0.20, facecolor="white", edgecolor=DB2_C,
                             linewidth=2.0, zorder=5))
    ax.add_patch(Ellipse((cx, top), w, 0.20, facecolor=DB2_C, edgecolor=DB2_C,
                         linewidth=2.0, zorder=6))


def icon_search(cx):
    chip(cx, OUT_C)
    ax.add_patch(Circle((cx - 0.06, ICON_CY + 0.05), 0.22, facecolor="white",
                        edgecolor=OUT_C, linewidth=3.0, zorder=4))
    ax.add_patch(FancyArrowPatch((cx + 0.09, ICON_CY - 0.10), (cx + 0.30, ICON_CY - 0.30),
                 arrowstyle="-", linewidth=4.0, color=OUT_C, zorder=4))


# ---- build cards ------------------------------------------------------------
specs = [
    (icon_image, "Image", "any JPEG / PNG", "multimodal input", IMG_C),
    (icon_cloud, "AWS Bedrock", "Titan Multimodal G1", "managed - 1024-d", AWS_C),
    (icon_db, "IBM Db2", "one row per image", "BLOB + VECTOR(1024)", DB2_C),
    (icon_search, "SQL search", "VECTOR_DISTANCE", "cosine - top-K", OUT_C),
]
for x, c, (draw, t, s1, s2, col) in zip(XS, CENTERS, specs):
    card(x, col)
    draw(c)
    label(c, t, s1, s2, col)

# ---- arrows + edge labels ---------------------------------------------------
edge_labels = ["base64", "1024-d vector", "store + query"]
for i in range(3):
    x0 = XS[i] + CARD_W + 0.06
    x1 = XS[i + 1] - 0.06
    ya = CY + CARD_H / 2
    ax.add_patch(FancyArrowPatch((x0, ya), (x1, ya), arrowstyle="-|>",
                 mutation_scale=22, linewidth=2.6, color=ARROW, zorder=1))
    ax.text((x0 + x1) / 2, ya + 0.26, edge_labels[i], ha="center", va="center",
            fontsize=10, color=SUB, fontweight="bold", zorder=5)

# ---- footer -----------------------------------------------------------------
ax.text(W / 2, 1.18, "Images and text share one vector space - search images with a text query, all inside Db2.",
        ha="center", va="center", fontsize=12, color=INK)
ax.text(W / 2, 0.62, "github.com/IBM/db2-multimodal-embedding", ha="center", va="center",
        fontsize=11.5, color=DB2_C, fontweight="bold")

out = "docs/workflow_linkedin.png"
fig.savefig(out, dpi=200, facecolor=CANVAS)
print("wrote", out)
