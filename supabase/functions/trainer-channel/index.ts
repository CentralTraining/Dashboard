import { authenticate, AccessError } from './access.ts';
import { FOLLOWER_SCOPE, FOLLOWER_BASELINE_DATE, recordFollowers, followerView } from './followers.ts';
// Official TikTok Display API only. Tokens never leave this function; no scraping.
const te=new TextEncoder(),td=new TextDecoder();
const ROOT='trainer-channel',TABLE='trainer_channel_private';
const SCOPES=['user.info.basic','user.info.profile','video.list'];
const ALLOWED=['https://centraltraining.github.io/Dashboard/','https://centraltraining.github.io/Test/'];
const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[Đđ]/g,'d').toLowerCase().replace(/[^a-z0-9]/g,'');
const clean=s=>String(s??'').trim();
const b64=a=>{const bytes=new Uint8Array(a);let out='';for(let i=0;i<bytes.length;i+=32768)out+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(out).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');};
const unb64=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
// The main dashboard uses the existing production credential variables.
const env=()=>({url:Deno.env.get('SUPABASE_URL'),secret:Deno.env.get('SUPABASE_SERVICE_ROLE_KEY'),
 client:Deno.env.get('TIKTOK_CLIENT_KEY')?.trim(),clientSecret:Deno.env.get('TIKTOK_CLIENT_SECRET')?.trim(),credentialSource:'legacy'});
const callback=()=>env().url+'/functions/v1/'+ROOT+'/oauth/callback';
const configured=()=>!!(env().client&&env().clientSecret);
const failure=(message,status=400)=>{throw new AccessError(message,status);};
async function cryptKey(){return crypto.subtle.importKey('raw',await crypto.subtle.digest('SHA-256',te.encode('trainer-channel-private-v1:'+env().secret)),'AES-GCM',false,['encrypt','decrypt']);}
async function seal(key,data){const iv=crypto.getRandomValues(new Uint8Array(12));return {v:1,iv:b64(iv),ciphertext:b64(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:te.encode(key)},await cryptKey(),te.encode(JSON.stringify(data))))};}
async function unseal(key,data){try{return JSON.parse(td.decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(data.iv),additionalData:te.encode(key)},await cryptKey(),unb64(data.ciphertext))));}catch{failure('Không đọc được dữ liệu kênh đã mã hóa.',503);}}
async function database(path,options={}){
 const e=env();if(!e.url||!e.secret)failure('Chưa sẵn sàng nơi lưu dữ liệu.',503);
 const r=await fetch(e.url+'/rest/v1/'+TABLE+path,{...options,headers:{apikey:e.secret,Authorization:'Bearer '+e.secret,'Content-Type':'application/json',Prefer:'return=representation',...options.headers},signal:AbortSignal.timeout(12000)});
 if(!r.ok)failure('Không lưu/đọc được dữ liệu Xây kênh. Hãy thử lại.',503);
 return r.status===204?[]:await r.json();
}
async function read(key){key=ROOT+':'+key;const rows=await database('?key=eq.'+encodeURIComponent(key)+'&select=key,value,version');return rows[0]?{key,version:rows[0].version,data:await unseal(key,rows[0].value)}:{key,version:null,data:null};}
async function put(record,data){
 if(!record.key.startsWith(ROOT+':'))record.key=ROOT+':'+record.key;
 const value=await seal(record.key,data),next=record.version===null?1:record.version+1;
 const rows=record.version===null?await database('',{method:'POST',headers:{Prefer:'resolution=ignore-duplicates,return=representation'},body:JSON.stringify({key:record.key,value,version:next,updated_at:new Date().toISOString()})}):await database('?key=eq.'+encodeURIComponent(record.key)+'&version=eq.'+record.version,{method:'PATCH',body:JSON.stringify({value,version:next,updated_at:new Date().toISOString()})});
 if(rows.length!==1)failure('Dữ liệu vừa thay đổi ở phiên khác. Hãy tải lại.',409);
 record.data=data;record.version=next;return record;
}
async function consume(key,version){const rows=await database('?key=eq.'+encodeURIComponent(key)+'&version=eq.'+version,{method:'DELETE'});if(rows.length!==1)failure('Liên kết kết nối đã được dùng. Hãy kết nối lại.',409);}
const validDate=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!Number.isNaN(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
function dates(body){if(!validDate(body.from)||!validDate(body.to)||body.to<body.from||(Date.parse(body.to)-Date.parse(body.from))/86400000>365)failure('Chọn khoảng ngày hợp lệ, tối đa 366 ngày.');return {from:body.from,to:body.to};}
function handle(value){let s=clean(value).replace(/^@/,'');if(/^https:\/\//i.test(s)){let u;try{u=new URL(s);}catch{failure('Link TikTok không hợp lệ.');}if(!['tiktok.com','www.tiktok.com'].includes(u.hostname)||!/^\/@[a-zA-Z0-9._]+\/?$/.test(u.pathname)||u.username||u.password)failure('Nhập link trang TikTok dạng https://www.tiktok.com/@tenkenh.');s=u.pathname.slice(2).replace(/\/$/,'');}if(!/^[a-zA-Z0-9._]{2,24}$/.test(s))failure('Tên kênh TikTok không hợp lệ.');return s.toLowerCase();}
function trainer(p,id,write=false){const t=p.trainers.find(t=>String(t.id)===String(id));if(!t||!(p.role==='admin'||(p.role==='trainer'&&norm(p.region)&&norm(t.region)===norm(p.region))))failure('Không có quyền truy cập Trainer này.',403);if(write&&p.role!=='admin'&&String(t.id)!==p.trainerId)failure('Chỉ được kết nối kênh của chính bạn.',403);return t;}
function roster(p){return p.trainers.filter(t=>p.role==='admin'||(norm(p.region)&&norm(t.region)===norm(p.region)));}
async function official(path,options,scopeProbe=false){
 let r;try{r=await fetch('https://open.tiktokapis.com'+path,{...options,signal:AbortSignal.timeout(20000)});}catch{failure('TikTok chưa phản hồi. Số liệu lần đồng bộ trước được giữ lại.',502);}
 let out;try{out=await r.json();}catch{failure('TikTok trả dữ liệu không hợp lệ.',502);}
 if(!r.ok||out.error?.code&&out.error.code!=='ok'||typeof out.error==='string'){
  if(scopeProbe&&(r.status===403||String(out.error?.code||'').includes('scope')))failure('Cần cấp quyền đọc follower.',403);
  failure(r.status===429?'TikTok đang giới hạn lượt truy cập. Hãy thử lại sau.':'Không lấy được dữ liệu TikTok. Hãy kiểm tra hoặc kết nối lại kênh.',r.status===429?429:502);
 }
 return out;
}
async function tokenCall(values){const e=env();return official('/v2/oauth/token/',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_key:e.client,client_secret:e.clientSecret,...values}).toString()});}
function tokenPayload(out,previous){
 if(!out.access_token||!out.refresh_token||!out.open_id||!Number.isFinite(Number(out.expires_in)))failure('TikTok chưa cấp quyền đọc video.',502);
 if(!SCOPES.every(s=>String(out.scope||'').split(',').includes(s)))failure('Cần đồng ý đủ quyền hồ sơ và video để kết nối.',403);
 if(previous&&previous.openId!==out.open_id)failure('Tài khoản TikTok trả về không khớp kênh đã gán.',403);
 return {access:out.access_token,refresh:out.refresh_token,openId:out.open_id,expires:Date.now()+Number(out.expires_in)*1000,scopes:String(out.scope||'').split(',').filter(Boolean)};
}
async function connect(body,p){
 const t=trainer(p,body.trainerId,true);if(!configured())failure('Chưa cấu hình ứng dụng TikTok. Xem hướng dẫn kết nối.',503);
 if(!ALLOWED.includes(body.returnUrl))failure('Địa chỉ quay lại không hợp lệ.');
 const rec=await read('channel:'+t.id);if(!rec.data?.handle)failure('Admin cần gán trang TikTok trước khi kết nối.');
 const state=crypto.randomUUID()+crypto.randomUUID();await put({key:'oauth:'+state,version:null},{trainerId:String(t.id),dashboardToken:body.dashboardToken,expected:rec.data.handle,returnUrl:body.returnUrl,expires:Date.now()+10*60000,version:rec.version});
 const requested=body.followerStats===true?[...SCOPES,FOLLOWER_SCOPE]:SCOPES;
 const url=new URL('https://www.tiktok.com/v2/auth/authorize/');url.search=new URLSearchParams({client_key:env().client,scope:requested.join(','),response_type:'code',redirect_uri:callback(),state,disable_auto_auth:'1'}).toString();
 return {url:url.href};
}
async function oauth(url){
 const state=url.searchParams.get('state')||'';if(!/^[a-f0-9-]{72}$/.test(state))failure('Phiên kết nối không hợp lệ.');
 const saved=await read('oauth:'+state);if(!saved.data||saved.data.expires<Date.now())failure('Phiên kết nối đã hết hạn. Hãy kết nối lại.');
 await consume(saved.key,saved.version);const back=saved.data.returnUrl;
 try{
  if(url.searchParams.has('error')||!url.searchParams.get('code'))throw Error();
  const current=await read('channel:'+saved.data.trainerId);if(!current.data||current.version!==saved.data.version||current.data.handle!==saved.data.expected)throw Error();
  // Recheck the authorizing dashboard account and current ownership at callback time.
  const owner=await authenticate(saved.data.dashboardToken);trainer(owner,saved.data.trainerId,true);
  const out=await tokenCall({grant_type:'authorization_code',code:url.searchParams.get('code'),redirect_uri:callback()});const token=tokenPayload(out);
  const info=await official('/v2/user/info/?fields=open_id,display_name,username',{headers:{Authorization:'Bearer '+token.access}});const profile=info.data?.user;
  if(!profile||profile.open_id!==token.openId||handle(profile.username)!==saved.data.expected)throw Error();
  const sameAccount=current.data.token?.openId===token.openId;
  let next={...current.data,token,profile:{username:handle(profile.username),displayName:clean(profile.display_name).slice(0,150)},
   snapshot:sameAccount?current.data.snapshot:null,pending:sameAccount?current.data.pending:null,
   followers:sameAccount?current.data.followers:null,
   followerBaseline:current.data.followerBaseline?.handle===saved.data.expected&&(!current.data.followerBaseline.openId||current.data.followerBaseline.openId===token.openId)?{...current.data.followerBaseline,openId:token.openId}:null};
  next=await captureFollowers(next);await put(current,next);
  return Response.redirect(back+'#channel-connect=ok',303);
 }catch{return Response.redirect(back+'#channel-connect=failed',303);}
}
const number=v=>{const n=Number(v);if(v===null||v===undefined||v===''||!Number.isSafeInteger(n)||n<0)failure('TikTok trả chỉ số chưa đầy đủ. Số liệu cũ được giữ lại.',502);return n;};
async function captureFollowers(channel){
 const knownScopes=Array.isArray(channel.token?.scopes);
 if(knownScopes&&!channel.token.scopes.includes(FOLLOWER_SCOPE)||!knownScopes&&channel.followers?.status==='needs_authorization')return {...channel,followers:{...channel.followers,status:'needs_authorization',lastAttemptAt:new Date().toISOString()}};
 try{
  const out=await official('/v2/user/info/?fields=open_id,follower_count',{headers:{Authorization:'Bearer '+channel.token.access}},true),profile=out.data?.user;
  if(!profile||profile.open_id!==channel.token.openId)throw Error('Follower account mismatch');
  const count=number(profile.follower_count),at=new Date().toISOString(),history=recordFollowers(channel.followers?.history,{at,count});
  return {...channel,token:knownScopes?channel.token:{...channel.token,scopes:[FOLLOWER_SCOPE],scopeSource:'stats_probe'},followers:{history,status:'ready',lastAttemptAt:at}};
 }catch(error){return {...channel,followers:{...channel.followers,status:error instanceof AccessError&&error.status===403?'needs_authorization':'unavailable',lastAttemptAt:new Date().toISOString()}};}
}
async function sync(body,p){
 const t=trainer(p,body.trainerId);if(!configured())failure('Chưa cấu hình ứng dụng TikTok.',503);
 const rec=await read('channel:'+t.id);let c=rec.data;if(!c?.token)failure('Trainer chưa kết nối TikTok.',409);
 if(!body.force&&c.snapshot?.complete&&Date.now()-Date.parse(c.snapshot.syncedAt)<15*60000&&!c.pending&&c.followers?.lastAttemptAt&&Date.now()-Date.parse(c.followers.lastAttemptAt)<15*60000)return {trainerId:String(t.id),cached:true,complete:true};
 if(c.token.expires<Date.now()+120000){const out=await tokenCall({grant_type:'refresh_token',refresh_token:c.token.refresh});c={...c,token:tokenPayload(out,c.token)};await put(rec,c);}
 // Keep follower observations even when a later video request fails.
 c=await captureFollowers(c);await put(rec,c);
 let pending=c.pending&&Date.now()-c.pending.started<10*60000?c.pending:{started:Date.now(),cursor:null,videos:[]};
 let complete=false;
 for(let page=0;page<5;page++){
  const payload={max_count:20,...(pending.cursor===null?{}:{cursor:pending.cursor})};
  const out=await official('/v2/video/list/?fields=id,create_time,title,like_count,share_count,view_count',{method:'POST',headers:{Authorization:'Bearer '+c.token.access,'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const d=out.data;if(!d||!Array.isArray(d.videos)||typeof d.has_more!=='boolean')failure('TikTok chưa trả danh sách video đầy đủ.',502);
  const map=new Map(pending.videos.map(v=>[v.id,v]));
  for(const v of d.videos){if(!/^\d{5,30}$/.test(String(v.id))||!Number.isFinite(Number(v.create_time)))failure('TikTok trả video không hợp lệ.',502);map.set(String(v.id),{id:String(v.id),createdAt:new Date(Number(v.create_time)*1000).toISOString(),title:clean(v.title).slice(0,500),likes:number(v.like_count),shares:number(v.share_count),views:number(v.view_count)});}
  pending.videos=[...map.values()];if(pending.videos.length>20000)failure('Kênh có quá nhiều video cho một lượt đồng bộ. Dữ liệu trước vẫn được giữ.',422);
  if(!d.has_more){complete=true;break;}
  if(!Number.isFinite(Number(d.cursor))||Number(d.cursor)===pending.cursor)failure('TikTok chưa trả trang video tiếp theo hợp lệ.',502);pending.cursor=Number(d.cursor);
 }
 if(complete){c={...c,snapshot:{complete:true,videos:pending.videos,syncedAt:new Date().toISOString()},pending:null};}
 else c={...c,pending};
 await put(rec,c);return {trainerId:String(t.id),complete,pagesPending:!complete,videoCount:pending.videos.length};
}
// Promote only an authorized Trainer's existing channel, without overwriting main
// records. Copy encrypted state server-side only when both connectors use the same
// TikTok client. Re-encrypt for the destination key; leave Test rows untouched.
async function channelForOverview(p,id){
 trainer(p,id);
 const target=await read('channel:'+id);
 if(target.data)return target;
 const overrideKey=Deno.env.get('TIKTOK_TEST_CLIENT_KEY'),overrideSecret=Deno.env.get('TIKTOK_TEST_CLIENT_SECRET');
 const testUsesOverride=overrideKey!==undefined||overrideSecret!==undefined;
 const sourceClient=(testUsesOverride?overrideKey:Deno.env.get('TIKTOK_CLIENT_KEY'))?.trim();
 if(!sourceClient||sourceClient!==env().client)return target;
 const sourceKey='trainer-channel-test:channel:'+id;
 const rows=await database('?key=eq.'+encodeURIComponent(sourceKey)+'&select=key,value,version');
 if(!rows[0])return target;
 const data=await unseal(sourceKey,rows[0].value);
 if(!data?.handle)return target;
 try{await put(target,data);}catch(error){
  if(!(error instanceof AccessError)||error.status!==409)throw error;
 }
 return await read('channel:'+id);
}
async function overview(body,p){
 const range=dates(body);const list=[];
 for(const t of roster(p)){
  const rec=await channelForOverview(p,t.id),c=rec.data;const videos=(c?.snapshot?.videos||[]).filter(v=>{const day=new Date(v.createdAt).toLocaleDateString('sv-SE',{timeZone:'Asia/Ho_Chi_Minh'});return day>=range.from&&day<=range.to;});
  list.push({id:String(t.id),name:clean(t.name),region:clean(t.region),handle:c?.handle||'',trackingFrom:c?.trackingFrom||null,connected:!!c?.token,known:!!c?.snapshot?.complete,syncedAt:c?.snapshot?.syncedAt||null,pending:!!c?.pending,videos,followers:followerView(c,range.from,range.to)});
 }
 return {trainers:list,role:p.role,ownTrainerId:p.trainerId,configured:configured(),...range};
}
async function assign(body,p){
 if(p.role!=='admin')failure('Chỉ Admin được gán trang TikTok.',403);const t=trainer(p,body.trainerId),name=handle(body.handle);
 if(!validDate(body.trackingFrom))failure('Ngày bắt đầu theo dõi không hợp lệ.');
 for(const other of p.trainers){if(String(other.id)!==String(t.id)&&(await read('channel:'+other.id)).data?.handle===name)failure('Trang TikTok này đã được gán cho Trainer khác.');}
 const rec=await read('channel:'+t.id),same=rec.data?.handle===name;
 await put(rec,{...(same?rec.data:{}),handle:name,trackingFrom:body.trackingFrom,updatedAt:new Date().toISOString()});return {saved:true,trainerId:String(t.id)};
}
async function setFollowerBaseline(body,p){
 if(p.role!=='admin')failure('Chỉ Admin được nhập mốc follower đầu kỳ.',403);
 const t=trainer(p,body.trainerId);
 if(!Number.isSafeInteger(body.count)||body.count<0)failure('Nhập số follower thực tế ngày 01/10/2026, là số nguyên không âm.');
 const rec=await read('channel:'+t.id);if(!rec.data?.handle)failure('Gán đúng kênh TikTok trước khi nhập mốc follower.');
 const baseline={date:FOLLOWER_BASELINE_DATE,count:body.count,source:'admin_record',recordedAt:new Date().toISOString(),handle:rec.data.handle,openId:rec.data.token?.openId||null};
 await put(rec,{...rec.data,followerBaseline:baseline});return {saved:true,trainerId:String(t.id),baseline:{date:baseline.date,count:baseline.count,source:baseline.source,recordedAt:baseline.recordedAt}};
}
Deno.serve(async req=>{
 const origin=req.headers.get('origin');const headers={'Content-Type':'application/json','Cache-Control':'no-store','Access-Control-Allow-Origin':origin==='https://centraltraining.github.io'?origin:'https://centraltraining.github.io','Access-Control-Allow-Headers':'content-type,apikey,authorization','Access-Control-Allow-Methods':'POST,OPTIONS','Vary':'Origin','Referrer-Policy':'no-referrer'};
 const respond=(out,status=200)=>new Response(JSON.stringify(out),{status,headers});
 try{
  const u=new URL(req.url);if(req.method==='GET'&&u.pathname.endsWith('/oauth/callback'))return await oauth(u);
  if(origin&&origin!=='https://centraltraining.github.io')return respond({error:'Nguồn truy cập không hợp lệ.'},403);
  if(req.method==='OPTIONS')return new Response(null,{status:204,headers});
  if(req.method!=='POST')return respond({error:'Chỉ hỗ trợ POST.'},405);
  if(Number(req.headers.get('content-length')||0)>8000)return respond({error:'Yêu cầu quá dài.'},413);
  const raw=await req.text();if(raw.length>8000)return respond({error:'Yêu cầu quá dài.'},413);let body;try{body=JSON.parse(raw);}catch{failure('Yêu cầu không hợp lệ.');}
  if(body.action==='status')return respond({ok:true,configured:configured(),credentialSource:env().credentialSource,redirectUri:callback(),scopes:SCOPES,optionalScopes:[FOLLOWER_SCOPE],followerHistory:true,followerBaselineDate:FOLLOWER_BASELINE_DATE});
  const p=await authenticate(body.dashboardToken);let out;
  switch(body.action){case 'overview':out=await overview(body,p);break;case 'assign':out=await assign(body,p);break;case 'connect':out=await connect(body,p);break;case 'sync':out=await sync(body,p);break;case 'set_follower_baseline':out=await setFollowerBaseline(body,p);break;default:failure('Thao tác không hợp lệ.');}
  return respond({ok:true,...out});
 }catch(e){return respond({error:e instanceof AccessError?e.message:'Chưa xử lý được yêu cầu Xây kênh. Dữ liệu cũ được giữ nguyên.'},e instanceof AccessError?e.status:500);}
});


