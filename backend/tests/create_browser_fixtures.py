import os
from pathlib import Path
import pymupdf
from test_documents import make_image

root = Path(os.environ["E2E_FIXTURE_DIR"])
root.mkdir(parents=True, exist_ok=True)
image = make_image()
(root / "plan.png").write_bytes(image)
for scanned, name in [(True, "scan.pdf"), (False, "text.pdf")]:
    pdf = pymupdf.open()
    page = pdf.new_page()
    if scanned:
        page.insert_image(pymupdf.Rect(0, 0, 595, 100), stream=image)
    else:
        page.insert_text((40, 80), "ORION budget is 4200000 yen. This is a text PDF paragraph.")
    (root / name).write_bytes(pdf.tobytes())
    pdf.close()
