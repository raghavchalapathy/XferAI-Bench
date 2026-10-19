'use strict';
(() => {
  const state = {track:'all',view:'methods',query:'',catalog:null};
  const $ = id => document.getElementById(id);
  function el(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; }
  function link(text,url){const n=el('a','',text);try{const u=new URL(url,location.href);if(!['https:','http:'].includes(u.protocol))return el('span','',text);n.href=u.href;n.target='_blank';n.rel='noopener noreferrer';}catch{return el('span','',text);}return n;}
  function pill(text,kind='neutral'){return el('span',`pill ${kind}`,text);}
  function list(items){const n=el('ul');for(const s of items||[])n.append(el('li','',s));return n;}
  function fits(n){return state.track==='all'||n.tracks.includes(state.track);}
  function matches(n){return !state.query||JSON.stringify(n).toLowerCase().includes(state.query);}
  function sourceLinks(sources){const n=el('div','dataset-links');for(const s of sources)n.append(link(`${s.id} · Primary source ↗`,s.url));return n;}
  function empty(title,body){const n=el('div','empty');n.append(el('h3','',title),el('p','',body));return n;}
  function methodRow(m){
    const row=el('div','method-row');const title=el('div');title.append(el('div','method-name',m.name),el('span','method-source',m.sources.map(s=>`${s.id} · ${s.version}`).join(' / ')));
    const status=el('div');status.append(pill('Review pending','amber'));
    const btn=el('button','row-button','View evidence +');btn.type='button';btn.setAttribute('aria-expanded','false');btn.setAttribute('aria-controls',`detail-${m.id}`);
    row.append(title,el('span','track',m.tracks.join(' / ')),status,btn);
    btn.addEventListener('click',()=>{const old=document.getElementById(`detail-${m.id}`);if(old){old.remove();btn.textContent='View evidence +';btn.setAttribute('aria-expanded','false');return;}
      const details=el('div','method-details');details.id=`detail-${m.id}`;details.append(el('p','',m.scope_basis));const columns=el('div','detail-columns');
      for(const [heading,items] of [['Why consider it',m.strengths],['What needs checking',m.limitations]]){const col=el('div');col.append(el('strong','',heading),list(items));columns.append(col);}
      details.append(columns,el('p','',`Evidence-backed inputs: ${m.features.map(x=>x.replaceAll('_',' ')).join(', ') || 'See the source protocol.'}`),el('p','',`${m.history_label}. No lab benchmark score or runtime is available.`),sourceLinks(m.sources));row.append(details);btn.textContent='Hide evidence −';btn.setAttribute('aria-expanded','true');
    });return row;
  }
  function field(parent,label,value){if(value===undefined||value===null)return;const p=el('p');p.append(el('strong','',`${label}: `),document.createTextNode(typeof value==='object'?JSON.stringify(value):String(value)));parent.append(p);}
  function paperRow(p){
    const row=el('article','paper-row'),top=el('div','paper-top'),body=el('div');body.append(el('h3','',p.title));const meta=el('div','paper-meta');meta.append(el('span','track',p.tracks.join(' / ')),pill(p.auxiliary_only?'Auxiliary profile only':'Provisional task fit','amber'),link('Read primary source ↗',p.url));body.append(meta,el('p','',p.recipe));top.append(el('span','year',p.first_public_year),body);row.append(top);
    const more=el('details'),d=el('div');more.append(el('summary','', 'Scope, strengths, limitations & reported result'));
    field(d,'Source version',p.version);field(d,'Read depth',p.read_depth);field(d,'Target',p.target_unit);field(d,'Horizon',p.horizon);field(d,'Locator',p.locator);
    d.append(el('strong','','Strengths'),list(p.strengths),el('strong','','Limitations'),list(p.limitations));
    if(p.paper_reported_result){d.append(el('strong','','Paper-reported result · not reproduced by this lab'));for(const [k,v] of Object.entries(p.paper_reported_result)){if(k!=='label'&&k!=='independent_review_status')field(d,k.replaceAll('_',' '),v);}d.append(el('p','','Do not rank this result against papers with different datasets, splits, horizons or inputs. Independent review is pending.'));}
    if(p.business_evidence){d.append(el('strong','','Business evidence, with attribution limits'));for(const [k,v] of Object.entries(p.business_evidence))field(d,k.replaceAll('_',' '),v);}
    more.append(d);row.append(more);return row;
  }
  function renderDatasets(){const grid=$('dataset-grid');grid.replaceChildren();const data=state.catalog.datasets.filter(fits);if(!data.length){grid.append(empty('No dataset record for this scenario yet.','The research queue can grow after direct evidence and access review.'));return;}
    for(const d of data){const card=el('article','dataset-card'),top=el('div','dataset-top');top.append(el('h3','',d.name),el('span','track',d.tracks.join(' / ')));card.append(top,pill('Access & rights review pending','amber'));const dl=el('dl');for(const [key,value] of [['Grain',d.native_grain||'See primary paper'],['History',d.history_rule],['Access',d.access]]){dl.append(el('dt','',key),el('dd','',value));}card.append(dl);if(d.product_count)card.append(el('p','',`${d.product_count.toLocaleString()} products${d.store_count?` · ${d.store_count} stores`:''}, as reported. Pin the exact release before benchmarking.`));for(const note of d.limitations||[])card.append(el('p','',note));card.append(sourceLinks(d.sources));grid.append(card);}}
  function render(){if(!state.catalog)return;const board=$('board');board.replaceChildren();if(state.view==='scores'){
    $('result-count').textContent='0 executed benchmarks · no performance rankings available';board.append(empty('The scored leaderboard is coming soon.','Candidates enter only after strict scope admission and comparable runs on the same dataset version, launch split, horizon, feature budget and metric definition. Paper-reported figures are available in the paper view.'));
  }else{const rows=state.catalog[state.view].filter(fits).filter(matches);$('result-count').textContent=`${rows.length} ${state.view==='methods'?(rows.length===1?'candidate recipe':'candidate recipes'):(rows.length===1?'paper record':'paper records')} · ${state.track==='all'?'all eligible history scenarios':state.track==='N0'?'zero-history launches':'launches with up to 28 calendar days of history'} · independent review pending`;
    if(!rows.length)board.append(empty('No matching evidence in the current catalog.','Try another search or scenario. A missing result is a research gap, not evidence that a method cannot work.'));
    else if(state.view==='methods'){const head=el('div','method-header');for(const t of ['METHOD / RECIPE','HISTORY','EVIDENCE STATE','DETAILS'])head.append(el('span','',t));board.append(head,...rows.map(methodRow));}
    else board.append(...rows.map(paperRow));}
    renderDatasets();
  }
  for(const btn of document.querySelectorAll('[data-track]'))btn.addEventListener('click',()=>{state.track=btn.dataset.track;for(const b of document.querySelectorAll('[data-track]'))b.setAttribute('aria-pressed',String(b===btn));render();});
  for(const btn of document.querySelectorAll('[data-view]'))btn.addEventListener('click',()=>{state.view=btn.dataset.view;for(const b of document.querySelectorAll('[data-view]'))b.setAttribute('aria-pressed',String(b===btn));render();});
  $('search').addEventListener('input',e=>{state.query=e.target.value.trim().toLowerCase();render();});
  fetch('assets/catalog.json').then(r=>{if(!r.ok)throw Error('Catalog request failed');return r.json();}).then(c=>{if(c.mode!=='literature_review'||c.summary.executed_benchmark_runs!==0||c.summary.independently_admitted_methods!==0)throw Error('This page requires a literature-only catalog.');state.catalog=c;$('method-count').textContent=c.summary.candidate_methods;$('dataset-count').textContent=c.summary.dataset_records;$('paper-count').textContent=c.summary.direct_task_fit_papers;$('catalog-date').textContent=`Provisional catalog · ${c.evidence_as_of}`;render();}).catch(()=>{$('result-count').textContent='The catalog could not be loaded.';$('board').replaceChildren(empty('Open this page through a web server.','Use the setup guide in the ZIP, or download catalog.json directly. No benchmark or recommendation has been run.'));});
})();
