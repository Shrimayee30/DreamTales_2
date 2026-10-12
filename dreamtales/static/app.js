'use strict';
const $ = id => document.getElementById(id);
const screens = ['home','loading','story','end-slide','error'];
const ambience = new DreamAmbience();
let session = null, current = null, timer = null, nextTimer = null, generation = 0;
let directionTarget = null;
let audio = null, utterance = null, playbackId = 0, speaking = false, paused = false, muted = false;
let queueing = false, finished = false;
let wordSpans = [], wordStarts = [], wordWeights = [], highlightedWord = -1;
function narrationSpeed() { return Math.min(1.5, Math.max(.6, Number($('narration-speed').value) || 1)); }
function highlightWord(index) {
  if (!$('read-along').checked) index = -1;
  if (index === highlightedWord) return;
  if (wordSpans[highlightedWord]) wordSpans[highlightedWord].classList.toggle('spoken-word', false);
  highlightedWord = index;
  if (wordSpans[index]) wordSpans[index].classList.toggle('spoken-word', true);
}
function renderWords(text) {
  wordSpans = []; wordStarts = []; wordWeights = []; highlightedWord = -1;
  $('scene-text').textContent = '';
  let offset = 0, total = 0;
  for (const part of text.split(/(\s+)/)) {
    if (!part) continue;
    if (/^\s+$/.test(part)) $('scene-text').append(document.createTextNode(part));
    else {
      const span = document.createElement('span'); span.textContent = part;
      wordStarts.push(offset); wordWeights.push(total);
      total += Math.max(2, part.replace(/[^a-z0-9]/gi, '').length) + (/[.!?]["”’']?$/.test(part) ? 4 : /[,;:]$/.test(part) ? 2 : 0);
      wordSpans.push(span); $('scene-text').append(span);
    }
    offset += part.length;
  }
  wordWeights.push(total);
}
function followAudio() {
  if (!audio || !speaking || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
  const progress = Math.min(.999999, Math.max(0, audio.currentTime / audio.duration));
  const position = progress * wordWeights[wordSpans.length];
  let index = 0;
  while (index + 1 < wordSpans.length && wordWeights[index + 1] <= position) index++;
  highlightWord(index);
}
function showSafety(message) {
  $('safety-message').textContent = message;
  if (!$('safety-dialog').open) $('safety-dialog').showModal();
}

const phases = {planning:'Planning a little adventure…',queued:'Your dream is next…',writing:'Dreaming up your story…',painting:'Finding a little moonlight…',narrating:'Preparing a gentle voice…',assembling:'Almost time to settle in…'};
function screen(name) { screens.forEach(id => {$(id).hidden = id !== name;}); }
async function api(path, options = {}) {
  const response = await fetch(path, {...options,headers:{'Content-Type':'application/json'}});
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    if (detail.code === 'child_safety') {
      const error = new Error(detail.detail); error.safety = true; error.status = response.status; throw error;
    }
    let message = 'Our story needs a little moment. Please try again.';
    if (response.status === 422) message = 'Try a gentle, imaginary story idea between 5 and 500 characters. Leave out personal details.';
    if (response.status === 409) message = 'That page has already turned. Your idea can join the following scene.';
    if (response.status === 429) message = 'The studio is busy. Please try again in a moment.';
    const error = new Error(message); error.status = response.status; throw error;
  }
  return response.status === 204 ? null : response.json();
}
function clearNext() { clearTimeout(nextTimer); nextTimer = null; }
function stopAudio() {
  ++playbackId; clearNext(); highlightWord(-1);
  if (audio) { audio.onended = null; audio.onerror = null; audio.ontimeupdate = null; audio.pause(); audio = null; }
  if (utterance) {utterance.onend = null; utterance.onerror = null; utterance.onboundary = null;}
  window.speechSynthesis?.cancel(); utterance = null; speaking = false; paused = false;
  $('narrate').textContent = '▶ Listen';
}
function pauseAudio() {
  clearNext();
  if (speaking) {if (audio) audio.pause(); else window.speechSynthesis?.pause(); paused = true; speaking = false;}
  $('narrate').textContent = paused ? '▶ Resume' : '▶ Listen';
  ambience.stop(); $('flow-status').textContent = 'Paused. Your story will wait for you.';
}
function localVoice() { return window.speechSynthesis?.getVoices().find(v => v.localService && v.lang.startsWith('en')); }
function updateVoiceNote() {
  if (!current) return;
  const available = !!current.audio.url || !!localVoice();
  $('narrate').disabled = !available; $('replay').disabled = !available;
  const names = {kokoro:'Kokoro · warm voice, unhurried pace',piper:'Local Piper narration','device-voice':'Offline device voice · natural narrator unavailable'};
  $('audio-note').textContent = available ? names[current.audio.kind] || 'Local narration' : 'No local voice is available. Read at your pace and use Continue now.';
}
function updateAmbience() {
  if (!current || $('story').hidden) return;
  ambience.update(current.ambience, {enabled:$('ambience-enabled').checked,muted,
    thunder:$('thunder-enabled').checked,volume:Number($('ambience-volume').value),duck:speaking});
}
function hasDraft() { return !!$('direction').value.trim() || document.activeElement === $('direction') || queueing; }
function scheduleNext() {
  clearNext();
  if ($('story').hidden || !current || current.ending || !finished) return;
  if (!$('autoplay').checked || muted || paused) { $('flow-status').textContent = 'Continue whenever you’re ready.'; return; }
  if (hasDraft()) { $('flow-status').textContent = 'Take your time. We’re holding the next scene for your idea.'; return; }
  const delay = 1200;
  $('flow-status').textContent = 'The next prepared scene is coming…';
  const token = generation;
  nextTimer = setTimeout(() => { if (token === generation && !hasDraft() && $('autoplay').checked && !muted) continueStory(); },delay);
}
async function playNarration() {
  if (!current || muted) { $('audio-note').textContent = 'Turn sound on when you’re ready to listen.'; return; }
  if (speaking) {pauseAudio();return;}
  const requestedScene = current, requestedGeneration = generation;
  await ambience.unlock().catch(() => {});
  if (requestedGeneration !== generation || requestedScene !== current || document.hidden) return;
  if (paused) {
    paused = false; speaking = true; $('narrate').textContent = 'Ⅱ Pause'; $('flow-status').textContent = $('autoplay').checked ? 'The next scene follows after this narration.' : 'Continue whenever you’re ready.'; updateAmbience();
    if (audio) audio.play().catch(() => {pauseAudio();$('audio-note').textContent='Tap Resume to listen.';});
    else window.speechSynthesis?.resume();
    return;
  }
  stopAudio(); finished = false;
  const id = playbackId, token = generation;
  const onEnd = () => {
    if (id !== playbackId || token !== generation) return;
    speaking = false; finished = true; highlightWord(-1); $('narrate').textContent = '↻ Listen again';
    if (current.ending) showEnding(); else {updateAmbience();scheduleNext();}
  };
  const onFail = () => {
    if (id !== playbackId || token !== generation) return;
    stopAudio(); ambience.stop(); $('audio-note').textContent = 'Tap Listen to start the voice. You can also read and continue yourself.';
  };
  speaking = true; $('narrate').textContent = 'Ⅱ Pause'; $('flow-status').textContent = $('autoplay').checked ? 'The next scene follows after this narration.' : 'Continue whenever you’re ready.'; updateAmbience();
  if (current.audio.url) {
    audio = new Audio(current.audio.url); audio.playbackRate = narrationSpeed(); audio.preservesPitch = true; audio.ontimeupdate = followAudio; audio.volume = Number($('volume').value);
    audio.onended = onEnd; audio.onerror = onFail; audio.play().then(() => {if (id === playbackId && token === generation) notifyPlaying();}).catch(onFail);
  } else {
    const voice = localVoice(); if (!voice) {onFail();return;}
    utterance = new SpeechSynthesisUtterance(current.narration); utterance.voice = voice;
    utterance.rate = .85 * narrationSpeed();
    utterance.onboundary = event => {
      if (id !== playbackId || token !== generation || !speaking) return;
      let index = 0;
      while (index + 1 < wordStarts.length && wordStarts[index + 1] <= event.charIndex) index++;
      highlightWord(index);
    }; utterance.volume = Number($('volume').value);
    utterance.onstart = () => {if (id === playbackId && token === generation) notifyPlaying();};
    utterance.onend = onEnd; utterance.onerror = onFail; window.speechSynthesis.speak(utterance);
  }
}
async function notifyPlaying() {
  const token = generation;
  try {
    const data = await api(`/api/sessions/${session}/playing`, {method:'POST',body:JSON.stringify({scene_id:current.scene_id})});
    if (token !== generation) return;
    directionTarget = data.direction_target;
    $('direction-hint').textContent = directionTarget ? `Your idea joins the next unwritten scene (currently scene ${directionTarget}).` : 'The remaining scenes are already being prepared.';
  } catch(error) { if(token===generation) $('flow-status').textContent = 'The next scene will prepare when you continue.'; }
}
function fail(error) {clearTimeout(timer);stopAudio();ambience.stop();$('error-text').textContent=error.message;$('retry').hidden=!session || !!error.safety;$('error-title').textContent=error.safety?'Let’s try a gentler dream.':'Our story needs a little moment.';screen('error');if(error.safety)showSafety(error.message);$(session && !error.safety?'retry':'recover').focus();}
function loading(phase) {
  screen('loading'); $('loading-title').textContent = phases[phase] || phases.writing;
  document.querySelectorAll('.pipeline li').forEach(el => el.classList.toggle('active',el.dataset.stage === phase));
}
async function poll(token) {
  if (token !== generation || !session) return;
  try {
    const data = await api(`/api/sessions/${session}`); if (token !== generation) return;
    if (data.phase === 'blocked') { const error = new Error(data.message); error.safety = true; throw error; }
    if (['ready','ending'].includes(data.phase)) {render(data);return;}
    if (['error','stopped'].includes(data.phase)) throw new Error('We couldn’t finish this scene. Your story and your next idea are still here. Try this scene again when you’re ready.');
    loading(data.phase);
    if (data.phase === 'planning') $('loading-title').textContent = 'Planning a story with a little lesson…';
    else if (!data.scene && data.phase !== 'error') $('loading-title').textContent = `Preparing your first two scenes… (${Math.min(2, data.prepared_scenes?.length || 0)} of 2 ready)`;
    timer = setTimeout(() => poll(token),650);
  } catch (error) {if (token === generation) fail(error);}
}
async function start(event) {
  event.preventDefault(); if (!$('dream-form').reportValidity()) return;
  const token = ++generation; $('home-message').textContent = ''; $('start').disabled = true;
  await ambience.unlock().catch(() => {}); if (token !== generation) { $('start').disabled = false; return; }
  loading('writing'); $('loading-title').focus();
  try {
    const data = await api('/api/sessions',{method:'POST',body:JSON.stringify({dream:$('dream').value,generation:{temperature:Number($('temperature').value),top_p:Number($('top-p').value),max_tokens:Number($('max-tokens').value)}})});
    if (token !== generation) {await api(`/api/sessions/${data.session_id}`,{method:'DELETE'});return;}
    session=data.session_id;await poll(token);
  } catch (error) {
    if (token === generation) {screen('home');$('home-message').textContent=error.message;$('dream').focus();if(error.safety)showSafety(error.message);}
  } finally {$('start').disabled=false;}
}
function showEnding() {
  if (!current?.ending) return;
  stopAudio(); ambience.stop(3);
  $('moral-text').textContent = current.moral || '';
  screen('end-slide'); $('end-title').focus();
}
function render(data) {
  stopAudio(); finished=false; current=data.scene; directionTarget=data.direction_target;
  $('chapter').textContent=`SCENE ${current.scene_id} OF ${data.total_scenes}`;
  $('scene-kicker').textContent=current.ending?'A SOFT PLACE TO REST':'SETTLE INTO YOUR STORY';
  $('scene-title').textContent=current.title;renderWords(current.story_text);
  $('location').textContent=current.location;$('scene-image').src=current.image.url;$('scene-image').alt=current.image.alt;
  $('moral-text').textContent=current.moral || '';
  $('moral-label').hidden=!current.moral;
  $('moral-text').hidden=!current.moral;
  $('continuation').hidden=current.ending;$('ending').hidden=!current.ending;
  $('direction').value='';$('direction-status').textContent='';
  $('flow-status').textContent='Upcoming scenes are being prepared while you listen.';
  $('direction-hint').textContent=directionTarget?`Your idea will begin in scene ${directionTarget}, as the next unwritten scene.`:'The story is settling into its ending.';
  const labels={rain:'Light rain',wind:'A soft breeze',night:'Night crickets',ocean:'Gentle waves',thunder:'Distant thunder (optional)'};
  $('soundscape-label').textContent=current.ambience.map(s=>labels[s]).join(' · ') || 'A quiet moment';
  $('source-note').textContent=current.image.kind === 'openai-image' ? 'Story imagined locally · Illustration generated with OpenAI' : 'Story imagined locally · Local illustration' + (current.image.fallback ? ' (hosted image unavailable)' : '');
  updateVoiceNote();screen('story');$('scene-title').focus();
  if (!muted && !document.hidden) playNarration();
}
async function continueStory() {
  if ($('story').hidden || !current || current.ending || queueing) return;
  // Explicit Continue includes any unsubmitted idea, so it cannot silently disappear.
  const direction=$('direction').value.trim(); const sceneId=current.scene_id;
  clearNext();stopAudio();ambience.stop(1.5);const token=++generation;
  loading('writing');$('loading-title').focus();
  try {
    await api(`/api/sessions/${session}/continue`,{method:'POST',body:JSON.stringify({scene_id:sceneId,direction})});
    if(token===generation)await poll(token);
  } catch(error) {
    if(token===generation && error.safety) fail(error);
    else if(token===generation && [409,422].includes(error.status)){screen('story');$('direction-status').textContent=error.message;$('direction').focus();}
    else if(token===generation)fail(error);
  }
}
async function queueDirection(event) {
  event.preventDefault(); if(!current || queueing) return;
  const value=$('direction').value.trim();if(!value){$('direction-status').textContent='Write a little idea first.';return;}
  clearNext();queueing=true;$('queue-direction').disabled=true;const token=generation;
  try {
    const result=await api(`/api/sessions/${session}/direction`,{method:'POST',body:JSON.stringify({scene_id:current.scene_id,direction:value})});
    if(token!==generation)return;
    $('direction').value='';$('direction-status').textContent=`Your idea is tucked into scene ${result.target_scene}.`;
    $('queue-direction').focus();
  } catch(error){if(token===generation){if(error.safety)fail(error);else $('direction-status').textContent=error.message;}}
  finally{queueing=false;$('queue-direction').disabled=false;if(token===generation)scheduleNext();}
}
async function retryScene() {
  if (!session) return;
  const token = ++generation;
  loading('writing'); $('loading-title').focus();
  try {
    const state = await api(`/api/sessions/${session}`);
    if (token !== generation) return;
    if (state.phase === 'error') {
      await api(`/api/sessions/${session}/retry`,{method:'POST',body:JSON.stringify({scene_id:state.completed_scene_id || 0})});
    }
    if (token === generation) await poll(token);
  } catch(error) {if (token === generation) fail(error);}
}
async function home() {
  ++generation;clearTimeout(timer);stopAudio();ambience.stop();const old=session;session=null;current=null;
  screen('home');$('dream').focus();
  if(old){try{await api(`/api/sessions/${old}`,{method:'DELETE'});}catch{}}
}
$('dream-form').addEventListener('submit',start);
$('retry').addEventListener('click',retryScene);
$('dream').addEventListener('input',()=>{$('dream-count').textContent=`${$('dream').value.length} / 500`;});
$('direction-form').addEventListener('submit',queueDirection);
$('direction').addEventListener('focus',()=>{clearNext();if(finished)$('flow-status').textContent='Take your time. The next scene will wait.';});
$('direction').addEventListener('input',()=>{clearNext();});
$('direction').addEventListener('blur',()=>{if(finished)scheduleNext();});
$('show-ending').addEventListener('click',showEnding);
$('back-to-scene').addEventListener('click',()=>{screen('story');$('scene-title').focus();});
$('continue').addEventListener('click',continueStory);
$('autoplay').addEventListener('change',scheduleNext);
['cancel','new-story','again','recover'].forEach(id=>$(id).addEventListener('click',home));
document.querySelector('.brand').addEventListener('click',event=>{event.preventDefault();home();});
$('narrate').addEventListener('click',playNarration);
$('replay').addEventListener('click',()=>{stopAudio();playNarration();});
$('volume').addEventListener('input',()=>{if(audio)audio.volume=Number($('volume').value);});
['ambience-volume','ambience-enabled','thunder-enabled'].forEach(id=>$(id).addEventListener('input',async()=>{await ambience.unlock().catch(()=>{});updateAmbience();}));
$('sound').addEventListener('click',()=>{muted=!muted;if(muted)pauseAudio();$('sound').setAttribute('aria-pressed',String(muted));$('sound').setAttribute('aria-label',muted?'Unmute all sound':'Mute all sound');$('sound').querySelector('span').textContent=muted?'Sound off':'Sound on';});
$('read-mode').addEventListener('click',()=>{const large=document.querySelector('.story-page').classList.toggle('large');$('read-mode').setAttribute('aria-pressed',String(large));$('read-mode').textContent=large?'Standard text Aa':'Larger text Aa';});
$('fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{$('fullscreen').title='Use your browser’s full-screen control.';}});
$('about').addEventListener('click',()=>{if(current)pauseAudio();$('about-dialog').showModal();});
['close-about','close-about-bottom'].forEach(id=>$(id).addEventListener('click',()=>$('about-dialog').close()));
if(window.speechSynthesis)window.speechSynthesis.onvoiceschanged=updateVoiceNote;
window.addEventListener('pagehide',()=>{stopAudio();ambience.stop();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseAudio();});
api('/api/health').then(data=>{$('mode').textContent=data.narrator==='kokoro'?'LOCAL STORIES · KOKORO VOICE':'LOCAL BEDTIME STORIES';$('about-mode').textContent=`Stories are generated locally with ${data.story_model || data.provider}. Narrator: ${data.narrator==='kokoro'?'Kokoro, warm and unhurried':data.narrator}. ${data.hosted_images_ready ? 'Illustrations use ' + data.image_model + ' through OpenAI; screened scene details are sent to that service.' : 'Illustrations currently use local drawings; hosted image generation is not active.'}`;}).catch(()=>{$('home-message').textContent='The local studio is offline. Start DreamTales and refresh this page.';$('start').disabled=true;});

const settingDefaults = {'temperature':'0.65','top-p':'0.9','max-tokens':'400'};
function showSetting(id) { $(id+'-value').textContent = id==='max-tokens' ? $(id).value : Number($(id).value).toFixed(2); }
Object.keys(settingDefaults).forEach(id => $(id).addEventListener('input',()=>showSetting(id)));
$('reset-settings').addEventListener('click',()=>{Object.entries(settingDefaults).forEach(([id,value])=>{$(id).value=value;showSetting(id);});});

$('narration-speed').addEventListener('input', () => {
  const rate = narrationSpeed();
  $('narration-speed-value').textContent = rate.toFixed(2) + '×';
  if (audio) audio.playbackRate = rate;
  if (utterance) $('audio-note').textContent = 'New speed applies when you replay or start the next scene with this device voice.';
});
$('read-along').addEventListener('change', () => {
  highlightWord(-1);
  if (audio && speaking) followAudio();
});
$('safety-close').addEventListener('click', () => {
  $('safety-dialog').close();
  if (session) home(); else $('dream').focus();
});
