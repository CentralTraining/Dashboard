import { AccessError } from './access.ts';
import { SANDBOX_IDS, sandboxId, sandboxCredentials } from './sandboxes.ts';
import { FOLLOWER_BASELINE_DATE, followerView } from './followers.ts';
// Team metrics are read-only; token ownership, callbacks and all mutations stay in the shared API.
const te=new TextEncoder(),td=new TextDecoder();
const ROOT='trainer-channel-test',TABLE='trainer_channel_private';
const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[Đđ]/g,'d').toLowerCase().replace(/[^a-z0-9]/g,'');
const clean=s=>String(s??'').trim();
const b64=a=>{const bytes=new Uint8Array(a);let out='';for(let i=0;i<bytes.length;i+=32768)out+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(out).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');};
const unb64=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
// Keep the original Sandbox credentials and route the second slot independently.
const env=(id='primary')=>({url:Deno.env.get('SUPABASE_URL'),secret:Deno.env.get('SUPABASE_SERVICE_ROLE_KEY'),...sandboxCredentials(id,k=>Deno.env.get(k))});
const callback=()=>env().url+'/functions/v1/'+ROOT+'/oauth/callback';
const configured=(id='primary')=>!!(env(id).client&&env(id).clientSecret);
const sandboxList=()=>SANDBOX_IDS.map(id=>({id,label:id==='primary'?'Sandbox 1':'Sandbox 2',configured:configured(id)}));
const channelSandbox=c=>{const id=sandboxId(c?.sandboxId);if(!id)failure('Sandbox của kênh không hợp lệ. Nhờ Admin kiểm tra.',409);return id;};
const failure=(message,status=400)=>{throw new AccessError(message,status);};
async function cryptKey(){return crypto.subtle.importKey('raw',await crypto.subtle.digest('SHA-256',te.encode('trainer-channel-private-v1:'+env().secret)),'AES-GCM',false,['decrypt']);}
async function unseal(key,data){try{return JSON.parse(td.decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(data.iv),additionalData:te.encode(key)},await cryptKey(),unb64(data.ciphertext))));}catch{failure('Không đọc được dữ liệu kênh đã mã hóa.',503);}}
async function database(path){
 const e=env();if(!e.url||!e.secret)failure('Chưa sẵn sàng nơi lưu dữ liệu.',503);
 const response=await fetch(e.url+'/rest/v1/'+TABLE+path,{method:'GET',headers:{apikey:e.secret,Authorization:'Bearer '+e.secret},signal:AbortSignal.timeout(12000)});
 if(!response.ok)failure('Chưa đọc được tiến độ Xây kênh. Hãy thử lại.',503);
 const rows=await response.json();if(!Array.isArray(rows))failure('Dữ liệu Xây kênh không hợp lệ.',503);return rows;
}
async function readAt(prefix,key){
 if(![ROOT,'trainer-channel'].includes(prefix))failure('Nguồn kết nối không hợp lệ.',400);
 key=prefix+':'+key;const rows=await database('?key=eq.'+encodeURIComponent(key)+'&select=key,value,version');
 return rows[0]?{key,version:rows[0].version,data:await unseal(key,rows[0].value)}:{key,version:null,data:null};
}
async function read(key){return readAt(ROOT,key);}
function mainCompatible(){
 const current=env('primary'),client=Deno.env.get('TIKTOK_CLIENT_KEY')?.trim(),secret=Deno.env.get('TIKTOK_CLIENT_SECRET')?.trim();
 return !!(client&&secret&&current.client===client&&current.clientSecret===secret);
}
const usableBaseline=(baseline,name)=>baseline?.date===FOLLOWER_BASELINE_DATE&&baseline.handle===name&&Number.isSafeInteger(baseline.count)&&baseline.count>=0;
function latestBaseline(local,main,token,name){
 const valid=value=>usableBaseline(value,name)&&(!value.openId||value.openId===token?.openId);
 const first=valid(local)?local:null,second=valid(main)?main:null;
 if(!first)return second;if(!second)return first;
 return (Date.parse(second.recordedAt)||0)>(Date.parse(first.recordedAt)||0)?second:first;
}
async function resolvedChannel(id){
 const local=await read('channel:'+id),c=local.data;
 if(channelSandbox(c)!=='primary'||!mainCompatible())return {local,data:c,source:'test'};
 const main=await readAt('trainer-channel','channel:'+id),m=main.data,token=m?.token;
 if(c?.token){const baseline=m?.handle===c.handle?latestBaseline(c.followerBaseline,m.followerBaseline,c.token,c.handle):c.followerBaseline;return {local,source:'test',data:{...c,followerBaseline:baseline}};}
 if(typeof token?.access!=='string'||!token.access||typeof token.refresh!=='string'||!token.refresh||!token.openId||typeof m?.handle!=='string'||!m.handle||sandboxId(m?.sandboxId)!=='primary'||sandboxId(token.sandboxId)!=='primary'||token.clientKey&&token.clientKey!==env('primary').client||c?.handle&&c.handle!==m.handle)
  return {local,data:c,source:'test'};
 const baseline=latestBaseline(c?.followerBaseline,m.followerBaseline,token,m.handle);
 if(baseline?.openId&&baseline.openId!==token.openId)return {local,data:c,source:'test'};
 // This is a server-side view. Never copy the active Main token into Test storage.
 return {local,source:'main',data:{...m,trackingFrom:c?.trackingFrom||m.trackingFrom,followerBaseline:baseline,sandboxId:'primary'}};
}
const validDate=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!Number.isNaN(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
function dates(body){if(!validDate(body.from)||!validDate(body.to)||body.to<body.from||(Date.parse(body.to)-Date.parse(body.from))/86400000>365)failure('Chọn khoảng ngày hợp lệ, tối đa 366 ngày.');return {from:body.from,to:body.to};}
export async function teamOverview(body,p){
 if(!['admin','trainer'].includes(p.role))failure('Không có quyền xem Xây kênh.',403);
 const range=dates(body);const list=[];
 for(const t of p.trainers){
  const resolved=await resolvedChannel(t.id),c=resolved.data;const videos=(c?.snapshot?.videos||[]).filter(v=>{const day=new Date(v.createdAt).toLocaleDateString('sv-SE',{timeZone:'Asia/Ho_Chi_Minh'});return day>=range.from&&day<=range.to;});
  list.push({id:String(t.id),name:clean(t.name),region:clean(t.region),handle:c?.handle||'',trackingFrom:c?.trackingFrom||null,canSync:p.role==='admin'||!!norm(p.region)&&norm(t.region)===norm(p.region),connected:!!c?.token,connectionSource:resolved.source,known:!!c?.snapshot?.complete,syncedAt:c?.snapshot?.syncedAt||null,pending:!!c?.pending,videos,followers:followerView(c,range.from,range.to),sandboxId:channelSandbox(c),sandboxReady:configured(channelSandbox(c)),needsSandboxReconnect:!!c?.token&&sandboxId(c.token.sandboxId)!==channelSandbox(c)});
 }
 return {trainers:list,overviewScope:'team',role:p.role,ownTrainerId:p.trainerId,configured:sandboxList().some(s=>s.configured),sandboxes:sandboxList(),...range};
}
