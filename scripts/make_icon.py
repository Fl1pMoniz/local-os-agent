"""
Generate authentic ASCII Aperture Science logo PNG and ICO assets.
Uses retro IBM BIOS font with 1:2 aspect correction to render a perfect 1:1 circular diaphragm.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

APERTURE_ASCII_LINES = [
    "              .,-:;//;:=,             ",
    "          . :H@@@MM@M#H/.,+%;,        ",
    "       ,/X+ +M@@M@MM%=,-%HMMM@X/,     ",
    "      -+@MM; $M@@MH+-,;XMMMM@MMMM@+-  ",
    "     ;@M@@M- XM@X;. -+XXXXXHHH@M@M#@/.",
    "   ,%MM@@MH ,@%=            .---=-=:=,.",
    "   -@#@@@MX .,              -%HX$$%%%+;",
    "  =-./@M@M$                  .;@MMMM@MM:",
    "  X@/ -$MM/                    .+MM@@@M$",
    " ,@M@H: :@:                    . -X#@@@@-",
    " ,@@@MMX, .                    /H- ;@M@M=",
    " .H@@@@M@+,                    %MM+..%#$.",
    "  /MMMM@MMH/.                  XM@MH; -; ",
    "   /%+%$XHH@$=              , .H@@@@MX,  ",
    "    .=--------.           -%H.,@@@@@MX,  ",
    "    .%MM@@@HHHXX$$$%+- .:$MMX -M@@MM%.  ",
    "      =XMMM@MM@MM#H;,-+HMM@M+ /MMMX=   ",
    "        =%@M@M#@$-.=$@MM@@@M; %M%=     ",
    "          ,:+$+-,/H#MMMMMMM@- -,      ",
    "                =++%%%%+/:-.          ",
]
clean_ascii = "\n".join(APERTURE_ASCII_LINES)

font_path = ROOT / "ui" / "fonts" / "PxPlus_IBM_BIOS-2y.ttf"
font = ImageFont.truetype(str(font_path), 20)

# Create 512x512 canvas for high-res ZimaOS / CasaOS app tile
img = Image.new("RGBA", (512, 512), (6, 4, 1, 255))
draw = ImageDraw.Draw(img)

# Outer rounded squircle frame
draw.rounded_rectangle(
    [(16, 16), (496, 496)],
    radius=64,
    fill=(10, 7, 3, 255),
    outline=(255, 157, 0, 180),
    width=3,
)

# Calculate text bounds to center exactly
bbox = draw.multiline_textbbox((0, 0), clean_ascii, font=font, spacing=2)
w = bbox[2] - bbox[0]
h = bbox[3] - bbox[1]

x = (512 - w) // 2 - bbox[0]
y = (512 - h) // 2 - bbox[1]

# Render ASCII Aperture diaphragm in phosphor amber
draw.multiline_text((x, y), clean_ascii, font=font, fill=(255, 157, 0, 255), spacing=2)

# Save high-res PNG for ZimaOS / CasaOS
assets_dir = ROOT / "ui" / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)

ascii_png = assets_dir / "aperture_ascii.png"
glados_png = assets_dir / "glados.png"
img.save(ascii_png, format="PNG")
img.save(glados_png, format="PNG")

# Also generate crisp favicon .ico
img.resize((64, 64), Image.Resampling.LANCZOS).save(assets_dir / "glados.ico", format="ICO")
print(f"Generated {ascii_png} and {glados_png} ({w}x{h}), and {assets_dir / 'glados.ico'}")
