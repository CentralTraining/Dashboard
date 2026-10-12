import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{parseNotice,verifySignature,sealNotice} from './worker.mjs';

const config={credentials:{appSecret:'fake-secret'},ledger_key:Buffer.alloc(32,3).toString('base64'),
  state:{conversation_id:'group',leader_staff_id:'leader',robot_code:'bot'},
  settings:{trainer_recipients:{a:{target:'trainer'}}},
  source:{url:'https://example.supabase.co',table:'kv_store',anon_key:'fake'}};
async function signed(body) {
  const timestamp=String(Date.now());
  const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(config.credentials.appSecret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const signature=Buffer.from(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(timestamp+'\n'+config.credentials.appSecret))).toString('base64');
  return new Request('https://receiver.example/',{method:'POST',headers:{timestamp,sign:signature},body:JSON.stringify(body)});
}

test('exact and relative deadlines agree; missing years and wrong dates are rejected',()=>{
  const now=Date.parse('2026-10-12T09:00:00+07:00');
  assert.equal(parseNotice('THÔNG BÁO\nNộp 2 video\nDeadline: 20/10/2026 17:00',now,now).deadline,Date.parse('2026-10-20T17:00:00+07:00')/1000);
  assert.equal(parseNotice('THÔNG BÁO\nNộp 2 video\nDeadline: 20/10/2026',now,now).shown,'23:59 · 20/10/2026');
  assert.throws(()=>parseNotice('THÔNG BÁO\nDeadline: ngày mai 20/10/2026 17:00',now,now),/không khớp/);
  assert.throws(()=>parseNotice('THÔNG BÁO\nDeadline: 20/10 17:00',now,now),/năm/);
  assert.throws(()=>parseNotice('THÔNG BÁO HỌP\nDeadline: 20/10/2026',now,now),/giờ họp/);
});

test('full Zoom URL, meeting ID and passcode are stored unchanged',()=>{
  const now=Date.parse('2026-10-12T09:00:00+07:00');
  const link='https://zoom.us/j/123?pwd=exact%2Btoken.1&source=team';
  const notice=parseNotice('THÔNG BÁO HỌP\nLink Zoom: '+link+'\nID cuộc họp: 123456\nMật mã: 001901\nThời gian: 14:00 20/10/2026',now,now);
  assert.ok(notice.content.includes(link));assert.ok(notice.content.includes('001901'));assert.ok(notice.content.includes('123456'));
});

test('signature rejects altered credentials and stale timestamps',async()=>{
  const request=await signed({});assert.equal(await verifySignature(request,'fake-secret'),true);
  assert.equal(await verifySignature(request,'wrong-secret'),false);
  assert.equal(await verifySignature(request,'fake-secret',Date.now()+600000),false);
});

test('journal is encrypted and only the configured group and leader can create',async t=>{
  const original=globalThis.fetch;let writes=0;
  globalThis.fetch=async (url,options)=>{
    const values=JSON.parse(options.body);writes++;return Response.json(values);
  };t.after(()=>{globalThis.fetch=original;});
  const context={waitUntil:()=>{}};const env={OLLIE_CONFIG_JSON:JSON.stringify(config)};
  const body={msgId:'notice-1',senderStaffId:'leader',conversationType:'2',conversationId:'group',robotCode:'bot',createAt:Date.now(),
    text:{content:'THÔNG BÁO\nNộp 2 video\nDeadline: 31/12/2099 17:00'}};
  assert.equal((await worker.fetch(await signed({...body,conversationId:'other'}),env,context)).status,403);
  assert.equal(writes,0);
  await worker.fetch(await signed({...body,senderStaffId:'trainer'}),env,context);assert.equal(writes,0);
  assert.equal((await worker.fetch(await signed(body),env,context)).status,200);assert.equal(writes,1);
  const value=await sealNotice({event_id:'x',original:'Secret Zoom password'},config);
  assert.ok(!JSON.stringify(value).includes('Secret Zoom password'));
  const cipher=Buffer.from(value.sealed,'base64');const key=await crypto.subtle.importKey('raw',Buffer.from(config.ledger_key,'base64'),'AES-GCM',false,['decrypt']);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:cipher.subarray(0,12),additionalData:new TextEncoder().encode('ollie-notices:v1:group')},key,cipher.subarray(12));
  assert.equal(JSON.parse(new TextDecoder().decode(plain)).original,'Secret Zoom password');
});
