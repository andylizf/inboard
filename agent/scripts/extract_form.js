(() => {
  if (!document.body || document.body.innerText.length < 500) return null;
  const out = [];
  const walk = (el) => {
    for (const c of el.children) {
      const tag = c.tagName.toLowerCase();
      if (tag === 'script' || tag === 'style') continue;
      if (['input','textarea','select','button','canvas'].includes(tag)) {
        const o = {tag, type: c.type || null, name: c.name || null, id: c.id || null,
          value: (c.value !== undefined ? String(c.value).slice(0,200) : null),
          checked: c.checked === true ? true : (c.checked === false ? false : null),
          disabled: c.disabled, readOnly: c.readOnly === true ? true : null,
          placeholder: c.placeholder || null, required: c.required || null,
          cls: (c.className||'').slice(0,120)};
        if (tag === 'select') o.options = [...c.options].map(x => x.text);
        if (tag === 'button') o.text = (c.innerText||'').trim();
        // label text for radio/checkbox
        if (o.type === 'radio' || o.type === 'checkbox') {
          let lab = c.closest('label');
          if (!lab && c.id) lab = document.querySelector('label[for="'+CSS.escape(c.id)+'"]');
          let t = lab ? lab.innerText.trim() : '';
          if (!t) { const p = c.parentElement; t = p ? p.innerText.trim() : ''; }
          o.optlabel = t.slice(0,200);
        }
        out.push(o);
      } else {
        // capture own text nodes
        const own = [...c.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent.replace(/\s+/g,' ').trim()).filter(Boolean).join(' ');
        if (own) out.push({tag:'TEXT', el:tag, cls:(c.className||'').slice(0,120), text: own.slice(0,400)});
        walk(c);
      }
    }
  };
  walk(document.body);
  return JSON.stringify(out);
})()
