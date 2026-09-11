'use strict';
const $=id=>document.getElementById(id);let courses=[],filtered=[],selected=new Set(),captured='',automatic=false,lastData='',knownCategories=[];
function normalized(c,index){
 const cells=Array.isArray(c._页面列)?c._页面列:[];
 const p=cells.findIndex(s=>String(s).includes(c.bjdm));
 const label=p>=0?String(cells[p]):String(c.name||'');
 const title=label.includes(c.bjdm)?label.split(c.bjdm)[0].trim():label;
 const teacher=p>=0?String(cells[p+3]||''):'';
 const capacity=cells.slice(-2).some(s=>String(s).includes('未满'))?'未满':cells.slice(-2).some(s=>String(s).includes('已满'))?'已满':'未知';
 return {...c,id:index,title,teacher,credits:p>=0?cells[p+2]:'',campus:p>=0?cells[p+5]:'',schedule:p>=0?cells[p+6]:'',capacity,conflict:label.includes('冲突'),category:String(c._分类||'未分类')};
}
function entry(c){return {name:c.title+(c.teacher?' / '+c.teacher:''),kcdm:c.kcdm,bjdm:c.bjdm,lx:String(c.lx),bqmc:String(c.bqmc),enabled:true};}
function load(data){
 if(!data||!Array.isArray(data.courses))throw Error('JSON 中缺少 courses 数组');
 const valid=data.courses.filter(c=>c&&typeof c.bjdm==='string'&&typeof c.kcdm==='string'&&c.lx!=null&&c.bqmc!=null);
 const previousCategory=$('category').value;
 courses=valid.map(normalized);selected.clear();captured=String(data.captured_at||'未标注');
 knownCategories=Array.from(new Set([...(Array.isArray(data.categories)?data.categories.map(c=>c.name):[]),...courses.map(c=>c.category)]));
 $('category').replaceChildren(new Option('全部分类',''),...knownCategories.map(x=>new Option(x,x)));
 if(knownCategories.includes(previousCategory))$('category').value=previousCategory;
 $('notes').textContent=[...(Array.isArray(data.notes)?data.notes:[]),`分类待确认 ${Array.isArray(data.unresolved)?data.unresolved.length:0} 条；缺少配置字段的条目不展示。`].join(' · ');
 $('table').hidden=false;render();
}
function cell(row,text,cls){const td=document.createElement('td');td.textContent=text??'';if(cls)td.className=cls;row.append(td);return td;}
function render(){
 const q=$('search').value.trim().toLowerCase();
 filtered=courses.filter(c=>(!q||JSON.stringify([c.title,c.teacher,c.bjdm,c.campus,c.schedule]).toLowerCase().includes(q))&&(!$('group').value||String(c.lx)===$('group').value)&&(!$('category').value||c.category===$('category').value)&&(!$('capacity').value||c.capacity===$('capacity').value)&&(!$('hideConflict').checked||!c.conflict));
 renderCategories();
 const fragment=document.createDocumentFragment();
 for(const c of filtered){const row=document.createElement('tr');const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(c.id);check.setAttribute('aria-label','勾选 '+c.title);check.onchange=()=>{check.checked?selected.add(c.id):selected.delete(c.id);updateSelection();};cell(row,'').append(check);
 const name=cell(row,'');const strong=document.createElement('strong');strong.textContent=c.title;name.append(strong);for(const text of [c.teacher,c.bjdm]){const small=document.createElement('small');small.textContent=text;name.append(small);}if(c.conflict){const x=document.createElement('span');x.textContent='时间冲突';x.className='conflict';name.append(x);}
 cell(row,c.category);cell(row,c.credits);cell(row,[c.campus,c.schedule].filter(Boolean).join('\n'),'schedule');const badge=document.createElement('span');badge.className='badge '+(c.capacity==='未满'?'open':c.capacity==='已满'?'full':'');badge.textContent=c.capacity;cell(row,'').append(badge);
 const button=document.createElement('button');button.textContent='复制配置';button.onclick=()=>copy(JSON.stringify(entry(c),null,2)+',');cell(row,'').append(button);fragment.append(row);}
 $('rows').replaceChildren(fragment);$('empty').hidden=filtered.length>0;$('summary').textContent=`显示 ${filtered.length} / ${courses.length} 个教学班 · 采集时间：${captured}`;updateSelection();
}
function updateSelection(){ $('countTotal').textContent=courses.length;$('countAvailable').textContent=courses.filter(c=>c.capacity==='未满').length;$('countSelected').textContent=selected.size;const n=filtered.filter(c=>selected.has(c.id)).length;$('all').checked=filtered.length>0&&n===filtered.length;$('all').indeterminate=n>0&&n<filtered.length;$('copySelected').textContent=`复制已勾选（${selected.size}）`;$('copySelected').disabled=!selected.size;}
async function copy(text){try{await navigator.clipboard.writeText(text);$('status').textContent='已复制配置片段（末尾含逗号）。粘贴为数组最后一项时请去掉末尾逗号。';}catch{$('copyText').value=text;$('copyDialog').showModal();$('copyText').focus();$('copyText').select();}}
$('search').oninput=render;for(const id of ['category','group','capacity','hideConflict'])$(id).onchange=render;
$('resetFilters').onclick=()=>{for(const id of ['search','category','group','capacity'])$(id).value='';$('hideConflict').checked=false;render();};
$('all').onchange=()=>{for(const c of filtered)$('all').checked?selected.add(c.id):selected.delete(c.id);render();};
$('clear').onclick=()=>{selected.clear();render();};
$('copySelected').onclick=()=>copy(courses.filter(c=>selected.has(c.id)).map(c=>JSON.stringify(entry(c),null,2)).join(',\n')+',');
$('closeDialog').onclick=()=>$('copyDialog').close();
$('file').onchange=async()=>{const file=$('file').files[0];if(!file)return;try{load(JSON.parse(await file.text()));automatic=false;$('status').textContent='已手动载入清单，自动更新已暂停；刷新页面恢复。';}catch(e){$('status').textContent='载入失败：'+e.message;}};
function waiting(message){courses=[];filtered=[];selected.clear();lastData='';$('rows').replaceChildren();$('table').hidden=true;$('categoryTabs').replaceChildren();$('notes').textContent='';$('summary').textContent='等待课程数据';$('status').textContent=message;updateSelection();}
async function poll(){
 if(!automatic)return;
 try{const response=await fetch('/api/courses',{cache:'no-store',signal:AbortSignal.timeout(5000)});if(!automatic)return;
  if(response.status===404){waiting('尚未找到 exports/course-list.json。采集成功后会自动展示。');}
  else if(!response.ok){waiting('课程文件暂不可读，等待下一次更新。');}
  else{const text=await response.text();if(!automatic)return;if(text!==lastData){load(JSON.parse(text));lastData=text;$('status').textContent='已载入最新课程清单。每 3 秒检查一次本地文件，更新后清空勾选。';}}
 }catch(e){if(automatic)waiting('暂时无法读取本地清单，稍后自动重试。');}
 finally{if(automatic)setTimeout(poll,3000);}
}
if(location.protocol==='http:'||location.protocol==='https:'){
 automatic=true;waiting('正在等待本地课程清单…');poll();
}else{
 waiting('请运行 scripts/查看课程列表，或在上方选择 course-list.json。未加载数据前不展示课程。');
}
function renderCategories(){
 const fragment=document.createDocumentFragment();
 for(const name of ['',...knownCategories]){
  const count=courses.filter(c=>(!name||c.category===name)&&(!$('group').value||String(c.lx)===$('group').value)).length;
  const button=document.createElement('button');
  button.type='button';button.className='category-tab';
  button.setAttribute('aria-pressed',String($('category').value===name));
  const text=document.createElement('span');text.textContent=name||'全部课程';
  const badge=document.createElement('span');badge.className='tab-count';badge.textContent=count;
  button.append(text,badge);button.onclick=()=>{$('category').value=name;render();};
  fragment.append(button);
 }
 $('categoryTabs').replaceChildren(fragment);
}
