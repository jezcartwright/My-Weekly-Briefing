#!/usr/bin/env python3
# Big PDF restructure (headers & footers unchanged):
#  - Page 1 = contents index (masthead + "In This Issue" + 2-col category grid
#    with each topic title and its page number).
#  - Pages 2+ = two expanded topics per page, each page led by the category band.
#  - Raw, clickable, category-coloured URLs shown under each reference and each
#    Go Deeper item (good for on-screen reading).
#  - Compact PDF type sizes so two full topics fit a page.
#  - Two-pass build keeps the index page numbers accurate even if a long pair
#    spills to one-per-page.
# Requires patch_amazon_linkcolour.py to have been applied first (uses bookToAmazon).
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

if 'function bookToAmazon(' not in s:
    raise SystemExit('bookToAmazon() not found — run patch_amazon_linkcolour.py first, then this. Aborting.')

# ---- helpers -------------------------------------------------------------
def replace_func(src, name, newcode):
    key = 'function ' + name + '('
    if src.count(key) != 1:
        raise SystemExit('function %s found %d times (expected 1).' % (name, src.count(key)))
    start = src.index(key)
    i = src.index('{', start)
    depth = 0
    j = i
    while j < len(src):
        c = src[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    return src[:start] + newcode + src[j:]

# ---- 1) CSS block: compact expanded-topic sizes + raw-URL + index classes
css_start_anchor = '.pdf-topic{'      # first occurrence = the base rule (others are @media overrides, left intact)
css_end_anchor = '.pdf-di a{'         # unique — bounds the region end
if s.count(css_end_anchor) != 1:
    raise SystemExit('.pdf-di a anchor not unique (%d). Aborting.' % s.count(css_end_anchor))
css_start = s.index(css_start_anchor)
css_end = s.index('}', s.index(css_end_anchor)) + 1
if not (0 <= css_start < css_end):
    raise SystemExit('CSS region bounds invalid. Aborting.')
old_css = s[css_start:css_end]
if old_css.count('{') < 15 or '.pdf-di::before' not in old_css:
    raise SystemExit('CSS region looks wrong (%d rules). Aborting.' % old_css.count('{'))

NEW_CSS = r""".pdf-topic{background:#fff;border:1px solid #E0D8CB;border-left:4px solid var(--orange);border-radius:1px;padding:14px 18px 12px;margin-bottom:0}
.pdf-topic:last-child{margin-bottom:0;border-bottom:1px solid #E0D8CB;border-left-width:4px}
.pdf-topic-head{display:flex;align-items:baseline;gap:10px;margin-bottom:3px}
.pdf-topic-num{font-family:'Inter',sans-serif;font-weight:700;font-size:10px;letter-spacing:.08em;color:var(--orange);flex-shrink:0;padding-top:3px}
.pdf-topic-title{font-family:'IBM Plex Serif',Georgia,'Times New Roman',serif;font-size:15px;font-weight:600;color:var(--t);margin:0;line-height:1.2;letter-spacing:-0.005em}
.pdf-topic-hl{font-family:'IBM Plex Serif',Georgia,'Times New Roman',serif;font-size:11.5px;color:var(--t2);margin:0 0 9px 22px;line-height:1.4;font-weight:500}
.pdf-two{display:grid;grid-template-columns:1.15fr 1fr;gap:18px;margin:0 0 9px 22px}
.pdf-lbl{font-family:'Inter',sans-serif;font-size:8.5px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:#8E857C;margin-bottom:5px}
.pdf-bt{font-size:9.5px;color:var(--t);line-height:1.45}
.pdf-bt + .ref,.pdf-bt + a.ref{display:block;margin-top:8px}
.pdf-it{font-family:'IBM Plex Serif',Georgia,'Times New Roman',serif;font-size:10px;font-style:italic;color:var(--t);line-height:1.4;border-left:none;padding-left:0;font-weight:500}
.pdf-attr{font-family:'Inter',sans-serif;font-size:9px;font-weight:400;color:var(--t2);margin-top:4px;display:block;font-style:normal;letter-spacing:0.01em}
.pdf-deeper{background:none;border-left:none;padding:8px 0 0 22px;border-top:1px solid #E0D8CB;border-radius:0;margin-top:3px}
.pdf-dlbl{font-family:'Inter',sans-serif;font-size:8.5px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--orange);margin-bottom:5px}
.pdf-di{font-size:9px;color:var(--t);margin-bottom:3px;display:flex;gap:8px;line-height:1.35;align-items:flex-start}
.pdf-di::before{content:"";display:inline-block;width:5px;height:5px;background:var(--bullet,var(--orange));flex-shrink:0;margin-top:5px}
.pdf-di a{color:var(--link,#A0530B);text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:0.5px}
.pdf-dicontent{flex:1;min-width:0;display:flex;flex-direction:column}
.pdf-ditext{display:block}
.pdf-rurl{display:block;font-family:'Inter',sans-serif;font-size:7.5px;line-height:1.3;color:var(--link,#A0530B);word-break:break-all;text-decoration:none;margin-top:1px;letter-spacing:.01em}
.pdf-ref{font-family:'Inter',sans-serif;font-size:8.5px;color:var(--t2);line-height:1.4;margin-top:7px;--link:#A0530B}
.pdf-reftext{display:block}
.pdf-ix-h{font-family:'IBM Plex Serif',Georgia,'Times New Roman',serif;font-size:19px;font-weight:600;color:var(--t);margin:4px 0 15px;letter-spacing:-0.01em}
.pdf-index{display:grid;grid-template-columns:1fr 1fr;column-gap:34px;row-gap:16px;align-items:start}
.pdf-ix-block{break-inside:avoid}
.pdf-ix-cat{font-family:'Inter',sans-serif;font-size:9.5px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;margin-bottom:7px;padding-bottom:5px;border-bottom:1px solid #E0D8CB}
.pdf-ix-row{display:flex;align-items:baseline;gap:8px;margin-bottom:6px}
.pdf-ix-t{font-family:'IBM Plex Serif',Georgia,'Times New Roman',serif;font-size:11px;font-weight:500;color:var(--t);line-height:1.3;flex:1}
.pdf-ix-p{font-family:'Inter',sans-serif;font-size:8.5px;color:#8E857C;flex-shrink:0;font-variant-numeric:tabular-nums}"""

s = s[:css_start] + NEW_CSS + s[css_end:]

# ---- 2) pdfTopicHTML (+ pdfLinkLine + pdfIndexHTML), raw visible URLs -----
NEW_TOPIC = r"""function pdfLinkLine(text,url){
  url=bookToAmazon(url);
  return '<span class="pdf-ditext">'+text+'</span>'+(url?'<a class="pdf-rurl" href="'+url+'" target="_blank" rel="noopener">'+url+'</a>':'');
}
function pdfIndexHTML(pageOf){
  var rows=Math.ceil(CATS.length/2),order=[];
  for(var r=0;r<rows;r++){ order.push(CATS[r]); if(CATS[r+rows])order.push(CATS[r+rows]); }
  var blocks=order.map(function(cat){
    var tops=gt(cat.id)||[];
    var rowsHtml=tops.map(function(t,i){
      var pg=(pageOf[cat.id]&&pageOf[cat.id][i])?pageOf[cat.id][i]:'';
      return '<div class="pdf-ix-row"><span class="pdf-ix-t">'+t.title+'</span><span class="pdf-ix-p">'+pg+'</span></div>';
    }).join('');
    return '<div class="pdf-ix-block"><div class="pdf-ix-cat" style="color:'+cat.color+'">'+cat.label+'</div>'+rowsHtml+'</div>';
  }).join('');
  return '<div class="pdf-ix-h">In This Issue</div><div class="pdf-index">'+blocks+'</div>';
}
function pdfTopicHTML(t,i,color){
  var ru=(t.ref&&t.ref.url)?bookToAmazon(t.ref.url):'';
  var refHtml=t.ref&&t.ref.text?'<div class="pdf-ref" style="--link:'+color+'"><span class="pdf-reftext">'+t.ref.text+'</span>'+(ru?'<a class="pdf-rurl" href="'+ru+'" target="_blank" rel="noopener">'+ru+'</a>':'')+'</div>':'';
  var deeperHtml=(t.deeper||[]).map(function(x){return '<div class="pdf-di" style="--bullet:'+color+';--link:'+color+'"><div class="pdf-dicontent">'+pdfLinkLine(x.text,x.url)+'</div></div>';}).join('');
  return '<div class="pdf-topic" style="border-left-color:'+color+'">'+
    '<div class="pdf-topic-head"><div class="pdf-topic-num" style="color:'+color+'">0'+(i+1)+'</div><div class="pdf-topic-title">'+t.title+'</div></div>'+
    '<div class="pdf-topic-hl">'+t.headline+'</div>'+
    '<div class="pdf-two"><div><div class="pdf-lbl">Why It Matters</div><div class="pdf-bt">'+t.why+'</div>'+refHtml+'</div>'+
    '<div><div class="pdf-lbl">Key Insight</div><div class="pdf-it">"'+t.insight+'"<span class="pdf-attr">\u2014 '+t.attribution+'</span></div></div></div>'+
    '<div class="pdf-deeper"><div class="pdf-dlbl" style="color:'+color+'">Go Deeper \u2192</div>'+deeperHtml+'</div>'+
  '</div>';
}"""
s = replace_func(s, 'pdfTopicHTML', NEW_TOPIC)

# ---- 3) pdfBuildSheets: two-pass (content first, index page prepended) ----
NEW_BUILD = r"""function pdfBuildSheets(scroll,dateStr){
  var mastSrc=document.querySelector('#pdf-mast-src .pdf-header');
  var contentSheets=[], pageOf={}, body=null, perPage=0;
  function newContentSheet(bandHtml){
    var sheet=document.createElement('div'); sheet.className='sheet';
    var h=document.createElement('div'); h.innerHTML=pdfRunHead(dateStr); sheet.appendChild(h.firstElementChild);
    body=document.createElement('div'); body.className='sheet-body'; sheet.appendChild(body);
    var f=document.createElement('div'); f.innerHTML=pdfFoot(); sheet.appendChild(f.firstElementChild);
    scroll.appendChild(sheet); contentSheets.push(sheet); perPage=0;
    if(bandHtml){ var bh=document.createElement('div'); bh.innerHTML=bandHtml; body.appendChild(bh.firstElementChild); }
  }
  CATS.forEach(function(cat){
    var tops=gt(cat.id); if(!tops||!tops.length)return;
    pageOf[cat.id]=[];
    var bandHtml='<div class="pdf-cat-title" style="background:'+cat.color+'">'+cat.label+'</div>';
    newContentSheet(bandHtml);
    for(var i=0;i<tops.length;i++){
      if(perPage>=2) newContentSheet(bandHtml);
      var holder=document.createElement('div'); holder.innerHTML=pdfTopicHTML(tops[i],i,cat.color);
      var node=holder.firstElementChild; if(!node)continue;
      body.appendChild(node);
      if(body.scrollHeight>body.clientHeight+1 && perPage>=1){
        body.removeChild(node); newContentSheet(bandHtml); body.appendChild(node);
      }
      perPage++;
      pageOf[cat.id][i]=contentSheets.length+1;
    }
  });
  var idx=document.createElement('div'); idx.className='sheet';
  if(mastSrc){ var m=mastSrc.cloneNode(true); var dd=m.querySelector('#pdf-date'); if(dd)dd.removeAttribute('id'); idx.appendChild(m); }
  var ib=document.createElement('div'); ib.className='sheet-body'; ib.innerHTML=pdfIndexHTML(pageOf); idx.appendChild(ib);
  var iff=document.createElement('div'); iff.innerHTML=pdfFoot(); idx.appendChild(iff.firstElementChild);
  scroll.insertBefore(idx, contentSheets[0]||null);
  var sheets=scroll.querySelectorAll('.sheet'), total=sheets.length;
  for(var sN=0;sN<sheets.length;sN++){ var pEl=sheets[sN].querySelector('.foot-page'); if(pEl)pEl.textContent='Page '+(sN+1)+' of '+total; }
}"""
s = replace_func(s, 'pdfBuildSheets', NEW_BUILD)

# ---- write ---------------------------------------------------------------
if len(s) < 300000:
    raise SystemExit('Result too small (%d bytes) — aborting.' % len(s))

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: PDF restructure applied. %d -> %d bytes (%+d).' % (orig_len, len(s), len(s) - orig_len))
