"""After a render process was killed: decode every PNG written in the last 3 minutes, remove the broken ones (caught
mid-write) so the resumed run renders them again.   python check_recent.py [folder=res_prod]"""
import glob
import os
import sys
import time

from PIL import Image

root = sys.argv[1] if len(sys.argv) > 1 else 'res_prod'
for f in glob.glob(os.path.join(root, '*', '*.png')):
    if time.time() - os.path.getmtime(f) < 180:
        try:
            with Image.open(f) as im:
                im.load()
        except Exception:  # noqa: BLE001
            print('BROKEN removed', f)
            os.remove(f)
print('recent renders checked')
