"""Generate Windows 95-inspired Alive Forever icons for runtime and packaging."""
from pathlib import Path

from PIL import Image, ImageDraw


def create_icon():
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    face = (212, 208, 200, 255)
    light = (255, 255, 255, 255)
    shadow = (128, 128, 128, 255)
    dark = (64, 64, 64, 255)
    title_blue = (0, 0, 128, 255)
    screen_teal = (0, 128, 128, 255)
    lightning = (255, 255, 0, 255)
    lightning_shadow = (128, 128, 0, 255)

    outer = (72, 72, 440, 440)
    draw.rectangle(outer, fill=face)
    draw.line([(outer[0], outer[3]), (outer[0], outer[1]), (outer[2], outer[1])], fill=light, width=8)
    draw.line([(outer[0] + 4, outer[3] - 4), (outer[0] + 4, outer[1] + 4), (outer[2] - 4, outer[1] + 4)], fill=light, width=4)
    draw.line([(outer[0], outer[3]), (outer[2], outer[3]), (outer[2], outer[1])], fill=dark, width=8)
    draw.line([(outer[0] + 4, outer[3] - 4), (outer[2] - 4, outer[3] - 4), (outer[2] - 4, outer[1] + 4)], fill=shadow, width=4)

    draw.rectangle((98, 98, 414, 150), fill=title_blue)
    draw.rectangle((110, 176, 402, 350), fill=screen_teal)
    draw.rectangle((106, 172, 406, 354), outline=shadow, width=4)

    bolt = [
        (250, 176),
        (320, 176),
        (276, 254),
        (334, 254),
        (224, 384),
        (250, 290),
        (190, 290),
    ]
    draw.polygon(bolt, fill=lightning)
    draw.line(bolt + [bolt[0]], fill=lightning_shadow, width=4)

    draw.rectangle((300, 360, 396, 408), fill=(0, 128, 0, 255))
    draw.line([(300, 408), (300, 360), (396, 360)], fill=light, width=4)
    draw.line([(300, 408), (396, 408), (396, 360)], fill=dark, width=4)

    output_png = Path('icon.png')
    output_ico = Path('icon.ico')

    img.save(output_png, 'PNG')
    icon_image = img.resize((256, 256), Image.Resampling.LANCZOS)
    icon_image.save(output_ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print('✓ Generated icon.png and icon.ico')

if __name__ == '__main__':
    create_icon()
