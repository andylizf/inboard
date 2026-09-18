import json,sys
d=json.load(open(sys.argv[1]))
items=None
for f in d['frames']:
    if f.get('value'):
        items=json.loads(f['value'])
for it in items:
    if it['tag']=='TEXT':
        print(f"TXT[{it['el']}|{it['cls']}] {it['text']}")
    elif it['tag']=='button':
        print(f"  BUTTON type={it['type']} text={it.get('text')!r} cls={it['cls']} disabled={it['disabled']}")
    else:
        print(f"  {it['tag'].upper()} type={it['type']} name={it['name']} id={it['id']} value={it['value']!r} checked={it['checked']} disabled={it['disabled']} ro={it['readOnly']} ph={it['placeholder']!r} req={it['required']} optlabel={it.get('optlabel')!r} opts={it.get('options')}")
