/* Actual-footage-only, offline browser video conversion. No app/model requests. */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const repo = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(repo, 'web/node_modules/playwright'));
const args = process.argv.slice(2);
const option = name => { const i=args.indexOf(name); return i<0 ? undefined : args[i+1]; };
const target = 90;
const sha = file => new Promise((resolve,reject)=>{const h=crypto.createHash('sha256');fs.createReadStream(file).on('data',d=>h.update(d)).on('error',reject).on('end',()=>resolve(h.digest('hex')))});
const stamp = s => {const n=Math.round(s*1000);return `${String(Math.floor(n/3600000)).padStart(2,'0')}:${String(Math.floor(n/60000)%60).padStart(2,'0')}:${String(Math.floor(n/1000)%60).padStart(2,'0')}.${String(n%1000).padStart(3,'0')}`;};
async function main(){
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu','--autoplay-policy=no-user-gesture-required']});
 let server;
 try {
  const page=await browser.newPage({viewport:{width:1280,height:720}});
  const capabilities=await page.evaluate(()=>({mp4:MediaRecorder.isTypeSupported('video/mp4;codecs=avc1.42E01E'),webm:MediaRecorder.isTypeSupported('video/webm;codecs=vp8'),canvasCapture:typeof HTMLCanvasElement.prototype.captureStream==='function'}));
  if(args.includes('--check-env')){console.log(JSON.stringify({status:'PREPARED_ONLY',capabilities,no_app_calls:true,no_inference_calls:true},null,2));return;}
  if(!option('--input')||!option('--timings')||!option('--out'))throw Error('Usage: node prepare-demo.cjs --input RAW.webm --timings STEPS.json --out backup-90s.mp4 [--captions] [--plan-only]');
  const input=path.resolve(option('--input'));const timingPath=path.resolve(option('--timings'));const output=path.resolve(__dirname,option('--out'));
  if(path.dirname(output)!==__dirname)throw Error('--out must be a filename within this owned demo directory');
  if(fs.existsSync(output))throw Error('Output exists; choose a new filename. Existing footage is never overwritten.');
  const extension=path.extname(output).toLowerCase();const mime=extension==='.mp4'?'video/mp4;codecs=avc1.42E01E':extension==='.webm'?'video/webm;codecs=vp8':null;
  if(!mime||!capabilities[extension.slice(1)]||!capabilities.canvasCapture)throw Error('Requested browser recording format unavailable. Use supported .webm, or report blocker; do not install a codec.');
  const timingText=fs.readFileSync(timingPath,'utf8');const data=JSON.parse(timingText);
  if(data.version!==1||data.source_kind!=='actual-browser-recording'||data.contains_mock_results!==false||data.audio!=='none'||typeof data.sample_photo_demonstration!=='boolean')throw Error('Actual-footage provenance is missing. Playwright backup is silent; audio-bearing sources require a separate audio-preserving workflow.');
  if(!Number.isFinite(data.duration_seconds)||data.duration_seconds<=0||!Array.isArray(data.segments)||!data.segments.length)throw Error('Duration or actual step timings missing. Do not invent timings.');
  let cursor=0;let waiting=0;let protectedTime=0;
  for(const s of data.segments){
   if(!['action','result','wait'].includes(s.kind)||!Number.isFinite(s.start)||!Number.isFinite(s.end)||s.end<=s.start||Math.abs(s.start-cursor)>.001)throw Error('Segments must cover the whole original timeline exactly once, without gaps or overlaps.');
   if(s.compressible&&s.kind!=='wait')throw Error('Only an explicitly marked wait may be compressed. Action/result segments remain at 1x.');
   if(s.caption!==undefined&&(typeof s.caption!=='string'||s.caption.includes('-->')||/[\r\n]/.test(s.caption)))throw Error('Caption must be one plain-text line.');
   if(s.kind==='wait'&&s.compressible===true)waiting+=s.end-s.start;else protectedTime+=s.end-s.start;
   cursor=s.end;
  }
  if(Math.abs(cursor-data.duration_seconds)>.05)throw Error('Step timings do not cover the full source.');
  // Reserve half a second for media end scheduling; hold the last real frame to 90s.
  const editingBudget=data.duration_seconds>target?89.5:target;
  const speed=data.duration_seconds>target?waiting/(editingBudget-protectedTime):1;
  if(data.duration_seconds>target&&(!waiting||protectedTime>=editingBudget||speed>16||speed<1))throw Error('Cannot fit 90s without cutting protected footage or exceeding 16x waits. Supply a shorter actual take or retime waits accurately.');
  let outputCursor=0;
  const segments=data.segments.map(s=>{const rate=s.kind==='wait'&&s.compressible===true?speed:1;const start=outputCursor;outputCursor+=(s.end-s.start)/rate;return {...s,speed:rate,output_start:start,output_end:outputCursor};});
  const sourceHash=await sha(input);
  const captionLabel=data.sample_photo_demonstration?'실제 브라우저 화면 · 샘플 사진 시연':'실제 브라우저 화면 녹화';
  const plan={status:'PREPARED_FOR_ACTUAL_FOOTAGE',source:input,source_sha256:sourceHash,timing_sha256:crypto.createHash('sha256').update(timingText).digest('hex'),target_seconds:target,source_seconds:data.duration_seconds,wait_speed:speed,protected_seconds:protectedTime,planned_hold_seconds:Math.max(0,target-outputCursor),segments,labels:[captionLabel,speed>1?'대기 구간만 압축 · 결과·클릭은 원속도':'원속도 재생 · 남은 시간은 마지막 실제 화면 유지'],audio:'silent Playwright recording; presenter narrates live',gpu_inference_calls:0};
  let streamError;
  server=http.createServer((req,res)=>{
   if(req.url==='/'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end('<!doctype html><meta charset=utf-8><title>Actual demo footage converter</title><video id=source muted playsinline preload=auto></video><canvas id=canvas width=1920 height=1080></canvas>');return;}
   if(req.url!=='/source.webm'&&req.url!=='/output'){res.writeHead(404);res.end();return;}
   const file=req.url==='/source.webm'?input:output;
   if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
   const size=fs.statSync(file).size;const range=req.headers.range;
   let start=0,end=size-1,status=200;
   if(range){const m=/^bytes=(\d+)-(\d*)$/.exec(range);if(!m){res.writeHead(416);res.end();return;}start=Number(m[1]);end=m[2]?Math.min(Number(m[2]),size-1):size-1;status=206;if(start>end||start>=size){res.writeHead(416);res.end();return;}}
   const headers={'Content-Type':file===input?'video/webm':extension==='.mp4'?'video/mp4':'video/webm','Content-Length':end-start+1,'Accept-Ranges':'bytes','Cache-Control':'no-store'};
   if(status===206)headers['Content-Range']=`bytes ${start}-${end}/${size}`;
   res.writeHead(status,headers);const readable=fs.createReadStream(file,{start,end});readable.on('error',e=>{streamError=e;res.destroy();});res.on('close',()=>readable.destroy());readable.pipe(res);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin=`http://127.0.0.1:${server.address().port}`;
  // This browser may access only the private local playback server, never the product/GPU.
  await page.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
  await page.goto(origin,{waitUntil:'load'});
  const actualDuration=await page.evaluate(async()=>{const v=document.querySelector('video');v.src='/source.webm';await new Promise((yes,no)=>{v.onloadedmetadata=yes;v.onerror=()=>no(Error('Source decode failed'));});return v.duration;});
  if(!Number.isFinite(actualDuration)||Math.abs(actualDuration-data.duration_seconds)>.75)throw Error(`Actual duration ${actualDuration} differs from timing file ${data.duration_seconds}.`);
  const base=output.slice(0,-extension.length);
  if([base+'.plan.json',base+'.vtt',base+'.receipt.json'].some(fs.existsSync))throw Error('Sidecar output exists; choose a new output basename.');
  fs.writeFileSync(base+'.plan.json',JSON.stringify(plan,null,2));
  fs.writeFileSync(base+'.vtt','WEBVTT\n\n'+segments.map((s,i)=>`${i+1}\n${stamp(s.output_start)} --> ${stamp(s.output_end)}\n${s.caption||s.kind}${s.speed>1?' · 대기 '+s.speed.toFixed(2)+'배 압축':''}\n`).join('\n'));
  if(args.includes('--plan-only')){console.log(JSON.stringify(plan,null,2));return;}
  console.log('Recording actual footage locally. Approximately 90 seconds; no app/model access.');
  const recorded=await page.evaluate(async({plan,mime,captions})=>{
   const video=document.querySelector('video'),canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
   await new Promise((resolve,reject)=>{if(video.readyState>=2)return resolve();video.onloadeddata=resolve;video.onerror=()=>reject(Error('Video decode failed'));});
   const stream=canvas.captureStream(30);const chunks=[];const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:6500000});
   const stopped=new Promise((resolve,reject)=>{recorder.onstop=resolve;recorder.onerror=e=>reject(Error(e.error?.message||'Recording error'));});
   recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
   const breakText=(text,y,maxWidth=1760)=>{ctx.font='28px "Malgun Gothic", sans-serif';let line='';for(const c of text){if(ctx.measureText(line+c).width>maxWidth){ctx.fillText(line,80,y);y+=35;line='';}line+=c;}ctx.fillText(line,80,y);};
   const draw=(s,holding)=>{ctx.fillStyle='#fff';ctx.fillRect(0,0,1920,1080);ctx.fillStyle='#302d27';ctx.font='bold 29px "Malgun Gothic", sans-serif';ctx.fillText(plan.labels[0],55,42);ctx.font='23px "Malgun Gothic", sans-serif';ctx.fillText(plan.labels[1],55,77);const scale=Math.min(1920/video.videoWidth,880/video.videoHeight),w=video.videoWidth*scale,h=video.videoHeight*scale;ctx.drawImage(video,(1920-w)/2,100+(880-h)/2,w,h);ctx.fillStyle='#4b6755';const label=holding?'마지막 실제 화면 유지':s.speed>1?`대기 구간 ${s.speed.toFixed(2)}배 압축`:s.kind==='result'?'실제 결과 · 원속도':'원속도';breakText(label+(captions&&s.caption?' · '+s.caption:''),1025);};
   let started=performance.now(),index=0,holding=false;
   draw(plan.segments[0],false);recorder.start(500);video.playbackRate=plan.segments[0].speed;await video.play();
   const mediaStart=performance.now();let endedAt=null;
   await new Promise((resolve,reject)=>{const loop=()=>{try{const elapsed=(performance.now()-started)/1000;if(elapsed>180)throw Error('Playback watchdog: original footage was not cut; recording blocked.');if(index<plan.segments.length-1&&video.currentTime>=plan.segments[index].end){index++;video.playbackRate=plan.segments[index].speed;video.currentTime=plan.segments[index].start;}const s=plan.segments[index];if(video.seeking||video.readyState<2){requestAnimationFrame(loop);return;}if(video.playbackRate!==s.speed)video.playbackRate=s.speed;if(video.ended&&!holding){holding=true;endedAt=elapsed;}draw(s,holding);if(holding&&elapsed>=plan.target_seconds){resolve();return;}requestAnimationFrame(loop);}catch(e){reject(e);}};loop();});
   recorder.stop();await stopped;stream.getTracks().forEach(t=>t.stop());
   const bytes=new Uint8Array(await new Blob(chunks,{type:mime}).arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
   return {base64:btoa(binary),seconds:(performance.now()-started)/1000,source_end_reached:video.ended,source_end_at:endedAt,segments_seen:index+1,media_start_delay_ms:mediaStart-started};
  },{plan,mime,captions:args.includes('--captions')});
  fs.writeFileSync(output,Buffer.from(recorded.base64,'base64'));
  const decoded=await page.evaluate(async()=>{const v=document.createElement('video');v.muted=true;v.src='/output';await new Promise((yes,no)=>{v.onloadedmetadata=yes;v.onerror=()=>no(Error('Output decode failed'));});return {duration:v.duration,width:v.videoWidth,height:v.videoHeight};});
  const unchanged=(await sha(input))===sourceHash;
  const okay=unchanged&&recorded.source_end_reached&&recorded.segments_seen===segments.length&&Number.isFinite(decoded.duration)&&Math.abs(decoded.duration-target)<1;
  const receipt={status:okay?'READY_FOR_HUMAN_REVIEW':'BLOCKED_REVIEW_OUTPUT',created_at:new Date().toISOString(),output,output_sha256:await sha(output),source_unchanged:unchanged,decoded,source_end_reached:recorded.source_end_reached,source_end_at:recorded.source_end_at,segments_seen:recorded.segments_seen,wait_speed:speed,source_sha256:sourceHash,captions:args.includes('--captions'),silent:true,no_product_or_model_requests:true,human_result_fidelity_review:'pending'};
  fs.writeFileSync(base+'.receipt.json',JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt,null,2));if(streamError)throw streamError;if(!okay)throw Error('Keep original. Output is not cleared: duration, completeness or source changed.');
 } finally {await browser.close();if(server)await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{console.error('BLOCKED: '+e.message);process.exitCode=1;});