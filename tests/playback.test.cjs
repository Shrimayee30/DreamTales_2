const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname,'../dreamtales/static');
function harness() {
  const elements = {};
  const el = id => elements[id] ||= {id,hidden:false,value:'',checked:true,disabled:false,textContent:'',dataset:{},
    listeners:{},classList:{toggle:()=>false},addEventListener(type,fn){this.listeners[type]=fn;},
    children:[],append(child){this.children.push(child);},setAttribute(){},querySelector(){return el(id+'-span');},focus(){document.activeElement=this;},
    reportValidity(){return true;},showModal(){this.open=true;},close(){this.open=false;}};
  const document = {hidden:false,activeElement:null,getElementById:el,
    createElement:()=>({textContent:'',classList:{toggle(){}}}),createTextNode:text=>({textContent:text}),querySelector:el,querySelectorAll:()=>[],listeners:{},addEventListener(type,fn){this.listeners[type]=fn;}};
  const timers = new Map(); let serial=0; const requests=[],players=[];
  class Audio {constructor(url){this.url=url;players.push(this);}play(){return Promise.resolve();}pause(){}}
  class Ambience {async unlock(){} update(){} stop(){} }
  const context = vm.createContext({document,Audio,DreamAmbience:Ambience,console,
    window:{speechSynthesis:{cancel(){},getVoices(){return[];}},addEventListener(){}},
    setTimeout(fn,ms){timers.set(++serial,{fn,ms});return serial;},clearTimeout(id){timers.delete(id);},
    fetch:async(url,options)=>{requests.push({url,options});return{ok:true,status:200,json:async()=>url==='/api/health'?{provider:'ollama',narrator:'kokoro'}:{phase:'writing'}};}});
  vm.runInContext(fs.readFileSync(path.join(root,'app.js'),'utf8'),context);
  el('volume').value='.8';el('ambience-volume').value='.2';el('thunder-enabled').checked=false;
  const run = code => vm.runInContext(code,context);
  const scene = {scene_id:1,title:'A quiet forest',story_text:'A peaceful scene.',narration:'A peaceful scene.',location:'Forest',image:{url:'/art.svg',alt:'Forest'},audio:{url:'/voice.wav',kind:'kokoro'},ambience:['rain'],ending:false};
  const show = async (overrides={},state={})=>{context.data={total_scenes:5,direction_target:3,checkpoint:false,...state,scene:{...scene,...overrides}};run("session='test'; render(data)");await new Promise(r=>setImmediate(r));};
  return {el,document,run,requests,players,timers,show,context};
}
test('narration end advances after a gap; no advance before it ends',async()=>{
  const h=harness();await h.show();assert.equal(h.timers.size,0);
  h.players[0].onended();const next=[...h.timers.values()].find(t=>t.ms===1200);assert.ok(next);
  next.fn();await new Promise(r=>setImmediate(r));assert.ok(h.requests.some(r=>r.url.endsWith('/continue')));
});
test('typing holds the next scene and manual continuation includes the draft',async()=>{
  const h=harness();await h.show();h.el('direction').value='Add Mr Rabbit';h.players[0].onended();
  assert.equal(h.timers.size,0);await h.run('continueStory()');
  const request=h.requests.find(r=>r.url.endsWith('/continue'));
  assert.equal(JSON.parse(request.options.body).direction,'Add Mr Rabbit');
});
test('pausing and disabling automatic continuation cancel countdowns',async()=>{
  const h=harness();await h.show();h.players[0].onended();assert.equal(h.timers.size,1);
  h.el('autoplay').checked=false;h.el('autoplay').listeners.change();assert.equal(h.timers.size,0);
  h.el('autoplay').checked=true;h.el('autoplay').listeners.change();assert.equal(h.timers.size,1);
  h.run('pauseAudio()');assert.equal(h.timers.size,0);
});
test('stale narration completion cannot advance a reset story',async()=>{
  const h=harness();await h.show();const lateEnd=h.players[0].onended;await h.run('home()');lateEnd();
  assert.equal(h.timers.size,0);assert.ok(!h.requests.some(r=>r.url.endsWith('/continue')));
});
test('playback failure does not skip a scene',async()=>{
  const h=harness();await h.show();h.players[0].onerror();assert.equal(h.timers.size,0);
  assert.match(h.el('audio-note').textContent,/Tap Listen/);
});
test('the final scene never automatically continues',async()=>{
  const h=harness();await h.show({ending:true,scene_id:5});h.players[0].onended();assert.equal(h.timers.size,0);
});
test('second scene continues without a batch checkpoint',async()=>{
  const h=harness();await h.show({scene_id:2},{checkpoint:true});h.players[0].onended();
  assert.ok([...h.timers.values()].some(t=>t.ms===1200));
  assert.match(h.el('flow-status').textContent,/next prepared scene/);
});
test('queued direction waits for narration to finish',async()=>{
  const h=harness();await h.show();h.el('direction').value='Add Mr Rabbit';
  await h.run('queueDirection({preventDefault(){}})');assert.ok(h.requests.some(r=>r.url.endsWith('/direction')));
  assert.ok(!h.requests.some(r=>r.url.endsWith('/continue')));assert.equal(h.timers.size,0);
  h.players[0].onended();assert.equal(h.timers.size,1);
});
test('sound buffers have bounded amplitudes and silent loop boundaries',()=>{
  const context=vm.createContext({console,window:{}});
  vm.runInContext(fs.readFileSync(path.join(root,'ambience.js'),'utf8'),context);
  const a=vm.runInContext('new DreamAmbience()',context);
  a.context={createBuffer(channels,n,rate){const data=new Float32Array(n);return {getChannelData:()=>data};}};
  for(const kind of ['rain','wind','night','ocean','thunder']){
    const samples=a.buffer(kind).getChannelData(0);
    let peak=0;for(const sample of samples){assert.ok(Number.isFinite(sample));peak=Math.max(peak,Math.abs(sample));}
    assert.ok(peak>0 && peak<1);assert.equal(Math.abs(samples[0]),0);assert.ok(Math.abs(samples[samples.length-1])<.001);
  }
});
test('a scene arriving in a hidden tab does not start audio',async()=>{
  const h=harness();h.document.hidden=true;await h.show();assert.equal(h.players.length,0);assert.equal(h.timers.size,0);
});
test('unsafe direction stops playback and hides retry',async()=>{
  const h=harness();await h.show();
  h.context.fetch=async()=>({ok:false,status:422,json:async()=>({code:'child_safety',detail:'This is not safe for kids.'})});
  h.el('direction').value='Add beer';
  await h.run('queueDirection({preventDefault(){}})');
  assert.equal(h.el('error').hidden,false);
  assert.equal(h.el('retry').hidden,true);
  assert.match(h.el('error-text').textContent,/not safe for kids/);
  assert.equal(h.timers.size,0);
  assert.equal(h.run('speaking'),false);
});
test('settings sliders display values and reset to defaults',()=>{
  const h=harness();
  h.el('temperature').value='1.1';
  h.el('temperature').listeners.input();
  assert.equal(h.el('temperature-value').textContent,'1.10');
  h.el('reset-settings').listeners.click();
  assert.equal(h.el('temperature').value,'0.65');
  assert.equal(h.el('top-p').value,'0.9');
  assert.equal(h.el('max-tokens').value,'400');
});
test('successful narration start requests background replenishment',async()=>{
  const h=harness();await h.show();
  const request=h.requests.find(r=>r.url.endsWith('/playing'));
  assert.ok(request);
  assert.equal(JSON.parse(request.options.body).scene_id,1);
  assert.ok(!h.requests.some(r=>r.url.endsWith('/continue')));
});
test('autoplay completes all five scenes without a manual click',async()=>{
  const h=harness();let sceneId=1;
  h.context.fetch=async(url,options)=>{
    h.requests.push({url,options});
    if(url.endsWith('/continue'))sceneId++;
    return {ok:true,status:200,json:async()=>({phase:sceneId===5?'ending':'ready',total_scenes:5,direction_target:Math.min(5,sceneId+3),checkpoint:false,scene:{...h.context.data.scene,scene_id:sceneId,ending:sceneId===5}})};
  };
  await h.show();
  for(let n=1;n<=5;n++){
    assert.equal(h.run('current.scene_id'),n);
    const player=h.players[h.players.length-1];player.onended();
    const next=[...h.timers.values()].find(t=>t.ms===1200);
    if(n===5){assert.equal(next,undefined);break;}
    assert.ok(next);next.fn();await new Promise(r=>setImmediate(r));
  }
  assert.equal(h.requests.filter(r=>r.url.endsWith('/continue')).length,4);
  assert.equal(h.requests.filter(r=>r.url.endsWith('/playing')).length,5);
});
test('moral slide appears only after final narration or explicit reading completion',async()=>{
  const h=harness();const moral='Sharing makes play more fun for everyone.';
  await h.show({scene_id:5,ending:true,moral});
  assert.equal(h.el('end-slide').hidden,true);
  h.players[0].onended();
  assert.equal(h.el('end-slide').hidden,false);
  assert.equal(h.el('story').hidden,true);
  assert.equal(h.el('moral-text').textContent,moral);
  assert.equal(h.requests.filter(r=>r.url.endsWith('/continue')).length,0);
  h.el('back-to-scene').listeners.click();
  assert.equal(h.el('story').hidden,false);
  h.el('show-ending').listeners.click();
  assert.equal(h.el('end-slide').hidden,false);
});
test('stale final audio cannot open the end slide after returning home',async()=>{
  const h=harness();await h.show({scene_id:5,ending:true,moral:'Be kind.'});
  const ended=h.players[0].onended;await h.run('home()');ended();
  assert.equal(h.el('end-slide').hidden,true);
});

test('speed changes apply immediately and persist across scenes and replay',async()=>{
  const h=harness();await h.show();
  h.el('narration-speed').value='0.65';h.el('narration-speed').listeners.input();
  assert.equal(h.players[0].playbackRate,.65);
  assert.equal(h.el('narration-speed-value').textContent,'0.65×');
  h.el('replay').listeners.click();await new Promise(r=>setImmediate(r));
  assert.equal(h.players.at(-1).playbackRate,.65);
  await h.show({scene_id:2});assert.equal(h.players.at(-1).playbackRate,.65);
});
test('highlight follows media time, pauses, clears, and can be disabled',async()=>{
  const h=harness();await h.show();const player=h.players[0];
  player.duration=12;player.currentTime=1;player.ontimeupdate();
  assert.equal(h.run('highlightedWord'),0);
  player.currentTime=11;player.ontimeupdate();assert.equal(h.run('highlightedWord'),2);
  h.run('pauseAudio()');player.currentTime=0;player.ontimeupdate();
  assert.equal(h.run('highlightedWord'),2);
  h.el('read-along').checked=false;h.el('read-along').listeners.change();
  assert.equal(h.run('highlightedWord'),-1);
  await h.run('home()');assert.equal(player.ontimeupdate,null);
});
test('unsafe initial prompt opens a clear dialog and keeps the prompt editable',async()=>{
  const h=harness();h.el('dream').value='A fox with beer';
  h.context.fetch=async()=>({ok:false,status:422,json:async()=>({code:'child_safety',detail:'This is not safe for kids.'})});
  await h.run('start({preventDefault(){}})');
  assert.equal(h.el('safety-dialog').open,true);
  assert.match(h.el('safety-message').textContent,/not safe/);
  assert.equal(h.el('home').hidden,false);
  h.el('safety-close').listeners.click();assert.equal(h.el('safety-dialog').open,false);
  assert.equal(h.document.activeElement,h.el('dream'));
});
