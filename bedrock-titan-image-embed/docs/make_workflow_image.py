"""Render the Bedrock -> Db2 workflow as a LinkedIn-optimized PNG.

Mirrors what embed_image.py actually does: read an image, get its embedding
from AWS Bedrock (Titan Multimodal), and store the image + the embedding in
IBM Db2. No similarity search happens in the script, so the diagram stops at
"stored in Db2". Written for people new to image embeddings.

Standalone (matplotlib only). Produces a 16:9 image at retina resolution
(2400x1350) that reads well in the LinkedIn feed.

    python3 docs/make_workflow_image.py     # -> docs/workflow_linkedin.png
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
ARROW = "#7c8b9a"      # muted slate for arrows
IMG_C = "#1f9e8f"      # teal   (image)
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

# ---- header -----------------------------------------------------------------
ax.text(W / 2, 6.20, "Turn an Image into a Vector and Store It in IBM Db2",
        ha="center", va="center", fontsize=22.5, fontweight="bold", color=INK)
ax.text(W / 2, 5.62, "Three steps: take a picture, turn it into numbers with AWS Bedrock, and save both in Db2.",
        ha="center", va="center", fontsize=13, color=SUB)

# ---- card layout (3 cards) --------------------------------------------------
CARD_W, CARD_H = 2.95, 2.70
CY = 2.30                       # bottom y of cards
GAP = (W - 1.0 - 3 * CARD_W) / 2.0
XS = [0.5 + i * (CARD_W + GAP) for i in range(3)]
CENTERS = [x + CARD_W / 2 for x in XS]
ICON_CY = CY + CARD_H - 0.80
TITLE_Y = CY + 0.96
SUB1_Y = CY + 0.58
SUB2_Y = CY + 0.28


def card(x, accent, step):
    ax.add_patch(FancyBboxPatch((x, CY), CARD_W, CARD_H,
                 boxstyle="round,pad=0.02,rounding_size=0.16",
                 linewidth=1.4, edgecolor=EDGE, facecolor=CARD, zorder=2))
    ax.add_patch(FancyBboxPatch((x + 0.24, CY + CARD_H - 0.12), CARD_W - 0.48, 0.07,
                 boxstyle="round,pad=0.01,rounding_size=0.03",
                 linewidth=0, facecolor=accent, zorder=3))
    # step-number badge (top-left) so beginners can follow the order
    bx, by = x + 0.40, CY + CARD_H - 0.40
    ax.add_patch(Circle((bx, by), 0.215, facecolor=accent, edgecolor="white",
                        linewidth=2.0, zorder=6))
    ax.text(bx, by, str(step), ha="center", va="center", fontsize=12.5,
            fontweight="bold", color="white", zorder=7)


def chip(cx, color):
    ax.add_patch(Circle((cx, ICON_CY), 0.42, facecolor=color, edgecolor="none",
                        alpha=0.16, zorder=3))


def label(cx, title, s1, s2, color):
    ax.text(cx, TITLE_Y, title, ha="center", va="center", fontsize=15.5,
            fontweight="bold", color=INK, zorder=4)
    ax.text(cx, SUB1_Y, s1, ha="center", va="center", fontsize=11.5, color=SUB, zorder=4)
    ax.text(cx, SUB2_Y, s2, ha="center", va="center", fontsize=11.5, color=color,
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


# ---- build cards ------------------------------------------------------------
specs = [
    (icon_image, "Your image", "a JPEG or PNG file", "what you start with", IMG_C),
    (icon_cloud, "AWS Bedrock", "the Titan AI model", "reads image → numbers", AWS_C),
    (icon_db, "IBM Db2", "one row stores both", "image + its vector", DB2_C),
]
for x, c, (draw, t, s1, s2, col), step in zip(XS, CENTERS, specs, (1, 2, 3)):
    card(x, col, step)
    draw(c)
    label(c, t, s1, s2, col)

# ---- arrows + plain-language labels -----------------------------------------
# Top line = the action; bottom line = what it means, for first-timers.
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

# ---- footer -----------------------------------------------------------------
ax.text(W / 2, 1.12,
        "An embedding is a list of numbers that captures what's in an image - similar pictures get similar numbers.",
        ha="center", va="center", fontsize=12, color=INK)
ax.text(W / 2, 0.60, "github.com/IBM/db2-multimodal-embedding", ha="center", va="center",
        fontsize=11.5, color=DB2_C, fontweight="bold")

out = "docs/workflow_linkedin.png"
fig.savefig(out, dpi=200, facecolor=CANVAS)
print("wrote", out)
