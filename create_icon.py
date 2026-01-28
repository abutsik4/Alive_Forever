"""Generate a polished Alive Forever app icon with a bold lightning bolt."""
from PIL import Image, ImageDraw

def create_icon():
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    cx, cy = size // 2, size // 2
    
    # Colors
    dark_outer = (15, 23, 42)
    dark_inner = (30, 41, 82)
    cyan = (0, 217, 255)
    cyan_mid = (80, 225, 255)
    cyan_light = (180, 245, 255)
    
    # Draw main circle with gradient
    for i in range(220, 0, -1):
        t = i / 220
        r = int(dark_outer[0] * t + dark_inner[0] * (1-t))
        g = int(dark_outer[1] * t + dark_inner[1] * (1-t))
        b = int(dark_outer[2] * t + dark_inner[2] * (1-t))
        draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(r, g, b, 255))
    
    # Glowing cyan ring
    ring_r = 200
    for glow in range(25, 0, -1):
        alpha = int(50 * (1 - glow/25))
        r = ring_r + glow
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(*cyan, alpha), width=2)
    for t in range(12):
        r = ring_r - t
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=cyan, width=2)
    for glow in range(10, 0, -1):
        alpha = int(70 * (1 - glow/10))
        r = ring_r - 12 - glow
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(*cyan, alpha), width=2)
    
    # BOLD LIGHTNING BOLT - proper thick shape
    # Using a wider, more substantial bolt design
    w = 35  # bolt width
    
    bolt = [
        (cx - w//2, cy - 140),     # top left
        (cx + w + 20, cy - 140),   # top right
        (cx + 10, cy - 10),        # middle upper right
        (cx + w + 10, cy - 10),    # notch outer right
        (cx + w//2, cy + 140),     # bottom right
        (cx - w - 20, cy + 140),   # bottom left
        (cx - 10, cy + 10),        # middle lower left
        (cx - w - 10, cy + 10),    # notch outer left
    ]
    draw.polygon(bolt, fill=cyan)
    
    # Middle highlight
    hw = 20
    highlight = [
        (cx - hw//2, cy - 120),
        (cx + hw + 10, cy - 120),
        (cx + 5, cy - 8),
        (cx + hw, cy - 8),
        (cx + hw//2, cy + 120),
        (cx - hw - 10, cy + 120),
        (cx - 5, cy + 8),
        (cx - hw, cy + 8),
    ]
    draw.polygon(highlight, fill=cyan_mid)
    
    # Bright core stripe
    cw = 8
    core = [
        (cx - cw//2, cy - 95),
        (cx + cw + 3, cy - 95),
        (cx + 2, cy - 5),
        (cx + cw, cy - 5),
        (cx + cw//2, cy + 95),
        (cx - cw - 3, cy + 95),
        (cx - 2, cy + 5),
        (cx - cw, cy + 5),
    ]
    draw.polygon(core, fill=cyan_light)
    
    img.save('icon.png', 'PNG')
    print('✓ Icon with BOLD lightning bolt created!')

if __name__ == '__main__':
    create_icon()
