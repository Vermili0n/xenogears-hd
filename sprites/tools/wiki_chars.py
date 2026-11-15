"""Xenogears characters and their images from the Xeno wiki (MediaWiki API, polite rate).

  python wiki_chars.py list  --out refs_wiki            -> refs_wiki/characters.json (title, images)
  python wiki_chars.py fetch --out refs_wiki [--max 12]  -> refs_wiki/<title>/<image files> (>= 96 px, no icons)
"""
import argparse
import json
import os
import re
import time

import requests

API = 'https://xenosaga.fandom.com/api.php'
UA = {'User-Agent': 'xeno-sprites-personal/1.0 (personal fan restoration; contact via owner)'}
SKIP = re.compile(r'(icon|logo|stub|flag|button|symbol|arrow|map|ost|cover|disc|sprite_sheet)', re.I)


def api(**p):
    p.update(format='json')
    for _ in range(4):
        r = requests.get(API, params=p, headers=UA, timeout=60)
        if r.ok:
            time.sleep(0.7)
            return r.json()
        time.sleep(5)
    r.raise_for_status()


def members(cat):
    out, cont = [], {}
    while True:
        j = api(action='query', list='categorymembers', cmtitle=f'Category:{cat}', cmlimit=500, cmtype='page', **cont)
        out += [m['title'] for m in j['query']['categorymembers']]
        if 'continue' not in j:
            return out
        cont = {'cmcontinue': j['continue']['cmcontinue']}


def page_images(titles):
    res = {t: [] for t in titles}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        cont = {}
        while True:
            j = api(action='query', prop='images|pageimages', titles='|'.join(chunk), imlimit=500, piprop='name', **cont)
            for p in j['query']['pages'].values():
                t = p['title']
                if t not in res:
                    continue
                if 'pageimage' in p:
                    main = 'File:' + p['pageimage'].replace('_', ' ')
                    if main not in res[t]:
                        res[t].insert(0, main)
                for im in p.get('images', []):
                    if im['title'] not in res[t]:
                        res[t].append(im['title'])
            if 'continue' not in j:
                break
            cont = {k: v for k, v in j['continue'].items() if k != 'continue'}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['list', 'fetch'])
    ap.add_argument('--out', default='refs_wiki')
    ap.add_argument('--max', type=int, default=12)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    idx = os.path.join(a.out, 'characters.json')
    if a.cmd == 'list':
        titles = sorted(set(members('Xenogears_characters')) | set(members('Xenogears_Playable_Characters')))
        imgs = page_images(titles)
        json.dump(imgs, open(idx, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(len(titles), 'characters;', sum(len(v) for v in imgs.values()), 'image refs')
        return
    imgs = json.load(open(idx, encoding='utf-8'))
    n = 0
    for t, files in imgs.items():
        files = [f for f in files if not SKIP.search(f) and re.search(r'\.(png|jpe?g|gif|webp)$', f, re.I)][:a.max]
        if not files:
            continue
        d = os.path.join(a.out, re.sub(r'[\\/:*?"<>|]', '_', t))
        os.makedirs(d, exist_ok=True)
        for i in range(0, len(files), 40):
            j = api(action='query', prop='imageinfo', titles='|'.join(files[i:i + 40]), iiprop='url|size')
            for p in j['query']['pages'].values():
                ii = (p.get('imageinfo') or [{}])[0]
                if not ii.get('url') or min(ii.get('width', 0), ii.get('height', 0)) < 96:
                    continue
                name = re.sub(r'[\\/:*?"<>|]', '_', p['title'][5:])
                dst = os.path.join(d, name)
                if os.path.exists(dst):
                    continue
                r = requests.get(ii['url'], headers=UA, timeout=120)
                if r.ok:
                    open(dst, 'wb').write(r.content)
                    n += 1
                time.sleep(0.7)
        print(t, len(os.listdir(d)), flush=True)
    print('downloaded', n)


if __name__ == '__main__':
    main()
