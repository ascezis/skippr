from pathlib import Path
from PIL import Image
from skippr_core.images import sanitize_filename, make_ambient_blur, fetch_image_for_item
from skippr_core.models import RowItem

def test_sanitize_filename():
    assert sanitize_filename("Linux / Torvalds : 1995") == "Linux_Torvalds_1995"
    assert sanitize_filename("___test___") == "test"
    assert sanitize_filename("") == "image"

def test_ambient_blur():
    # Test RGB square
    img_rgb = Image.new("RGB", (500, 500), color=(255, 0, 0))
    res_rgb = make_ambient_blur(img_rgb, target_w=1920, target_h=1080)
    assert res_rgb.size == (1920, 1080)

    # Test Palette (P) mode - previously caused ValueError: image has wrong mode
    img_p = img_rgb.convert("P")
    res_p = make_ambient_blur(img_p, target_w=1920, target_h=1080)
    assert res_p.size == (1920, 1080)

    # Test RGBA mode with transparency
    img_rgba = Image.new("RGBA", (400, 600), color=(0, 255, 0, 128))
    res_rgba = make_ambient_blur(img_rgba, target_w=1920, target_h=1080)
    assert res_rgba.size == (1920, 1080)

def test_fetch_image_dry_run(tmp_path):
    item = RowItem(
        n=15,
        block="Intro",
        phrase="Test phrase",
        kind="картинка",
        reference="Futurama Fry",
        query="Futurama Fry not sure if meme",
    )
    ok, fpath, msg = fetch_image_for_item(item, clips_dir=tmp_path, dry_run=True)
    assert ok is True
    assert fpath is not None
    assert "Dry-run" in msg
