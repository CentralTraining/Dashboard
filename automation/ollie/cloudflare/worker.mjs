const encoder = new TextEncoder();
const json = (value, status = 200) => Response.json(value, {status});
const bytes = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));
const base64 = value => btoa(String.fromCharCode(...new Uint8Array(value)));
const fold = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
async function hash(value) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value))), b => b.toString(16).padStart(2, '0')).join('');
}

export async function verifySignature(request, appSecret, now = Date.now()) {
  const stamp = request.headers.get('timestamp') || '';
  const sign = request.headers.get('sign') || '';
  if (!/^\d{13}$/.test(stamp) || Math.abs(Number(stamp) - now) > 300000) return false;
  try {
    const key = await crypto.subtle.importKey('raw', encoder.encode(appSecret), {name:'HMAC', hash:'SHA-256'}, false, ['verify']);
    return await crypto.subtle.verify('HMAC', key, bytes(decodeURIComponent(sign)), encoder.encode(stamp + '\n' + appSecret));
  } catch { return false; }
}

export function parseNotice(text, sourceTime, now = Date.now()) {
  const lines = text.normalize('NFC').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const dueLines = lines.filter(line => /(?:deadline|han hoan thanh|han chot|thoi gian)\s*:/.test(fold(line)));
  if (dueLines.length !== 1) throw new Error('Mỗi thông báo cần một dòng Deadline hoặc Hạn hoàn thành rõ ràng.');
  const line = fold(dueLines[0]);
  const clock = [...line.matchAll(/(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)/g)];
  if (clock.length > 1) throw new Error('Thông báo có nhiều giờ; hãy tách từng việc và deadline.');
  if (!clock.length && /\bhop\b|\bmeeting\b/.test(fold(lines[0]))) throw new Error('Thông báo họp cần cả giờ họp, ví dụ 14:00.');
  const dayMonth = line.match(/(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?!\d)/);
  const iso = line.match(/(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)/);
  const relative = line.includes('ngay mai') ? 1 : line.includes('hom nay') ? 0 : line.includes('ngay kia') ? 2 : null;
  let year, month, day;
  const anchor = new Date(sourceTime + 7 * 3600000);
  if (dayMonth) [day, month, year] = dayMonth.slice(1).map(Number);
  else if (iso) [year, month, day] = iso.slice(1).map(Number);
  else if (relative !== null) {
    anchor.setUTCDate(anchor.getUTCDate() + relative);
    [year, month, day] = [anchor.getUTCFullYear(), anchor.getUTCMonth() + 1, anchor.getUTCDate()];
    const short = line.match(/(?<!\d)(\d{1,2})[./](\d{1,2})(?![\d./])/);
    if (short && (Number(short[1]) !== day || Number(short[2]) !== month)) throw new Error('Ngày tương đối và ngày/tháng không khớp.');
  } else throw new Error('Deadline cần ngày/tháng/năm, ví dụ 20/10/2026 17:00.');
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() + 1 !== month || date.getUTCDate() !== day) throw new Error('Ngày deadline không hợp lệ.');
  if (relative !== null && (dayMonth || iso)) {
    const expected = new Date(sourceTime + 7 * 3600000); expected.setUTCDate(expected.getUTCDate() + relative);
    if (expected.getUTCFullYear() !== year || expected.getUTCMonth() + 1 !== month || expected.getUTCDate() !== day) throw new Error('Ngày tương đối và ngày cụ thể không khớp.');
  }
  const weekdays = ['chu nhat','thu hai','thu ba','thu tu','thu nam','thu sau','thu bay'];
  weekdays.forEach((label, index) => { if (new RegExp('\\b' + label + '\\b').test(line) && date.getUTCDay() !== index) throw new Error('Thứ trong tuần không khớp với ngày deadline.'); });
  const hour = clock.length ? Number(clock[0][1]) : 23;
  const minute = clock.length ? Number(clock[0][2]) : 59;
  const deadline = Date.UTC(year, month - 1, day, hour - 7, minute);
  if (deadline <= now) throw new Error('Deadline đã qua; hãy gửi thời hạn mới.');
  const content = lines.filter(value => value !== dueLines[0] && !/^(?:dear|xin chao|anh em sap xep|hen gap)\b/.test(fold(value)))
    .map(value => value.replace(/^.*?thông báo\s*/i, '').trim()).filter(Boolean).join('\n');
  if (!content || content.length > 12000) throw new Error('Hãy rút gọn hoặc tách thông báo theo từng deadline.');
  return {content, deadline: deadline / 1000, shown: `${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')} · ${String(day).padStart(2,'0')}/${String(month).padStart(2,'0')}/${year}`};
}

export async function sealNotice(event, config) {
  const raw = bytes(config.ledger_key);
  if (raw.length !== 32) throw new Error('invalid_notice_key');
  const key = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt']);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aad = encoder.encode('ollie-notices:v1:' + config.state.conversation_id);
  const cipher = new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM', iv:nonce, additionalData:aad, tagLength:128}, key, encoder.encode(JSON.stringify(event))));
  const sealed = new Uint8Array(nonce.length + cipher.length); sealed.set(nonce); sealed.set(cipher, nonce.length);
  return {version:1, sealed:base64(sealed)};
}

function sourceEndpoint(config) {
  const url = new URL(config.source.url);
  if (url.protocol !== 'https:' || !url.hostname.endsWith('.supabase.co') || !/^[a-zA-Z0-9_]+$/.test(config.source.table)) throw new Error('invalid_source');
  return new URL('/rest/v1/' + config.source.table, url);
}

async function storeNotice(event, config) {
  const key = 'ollieNotice:' + await hash(event.event_id);
  const value = await sealNotice(event, config);
  const response = await fetch(sourceEndpoint(config), {method:'POST', headers:{
    apikey:config.source.anon_key, Authorization:'Bearer ' + config.source.anon_key,
    'Content-Type':'application/json', Prefer:'resolution=ignore-duplicates,return=representation'},
    body:JSON.stringify([{key, value, updated_at:new Date().toISOString()}])});
  if (!response.ok) throw new Error('notice_write_failed');
  const rows = await response.json();
  if (!Array.isArray(rows) || rows.length > 1) throw new Error('notice_write_unconfirmed');
  if (rows.length === 1) {
    if (rows[0].key !== key || rows[0].value?.sealed !== value.sealed) throw new Error('notice_write_unconfirmed');
    return true;
  }
  // Confirm an existing identity instead of claiming a swallowed write succeeded.
  const existing = sourceEndpoint(config); existing.searchParams.set('key', 'eq.' + key); existing.searchParams.set('select','key');
  const check = await fetch(existing, {headers:{apikey:config.source.anon_key, Authorization:'Bearer ' + config.source.anon_key}});
  if (!check.ok || (await check.json()).length !== 1) throw new Error('notice_write_unconfirmed');
  return false;
}

async function replySession(body, text) {
  if (!body.sessionWebhook) return;
  const url = new URL(body.sessionWebhook);
  if (url.protocol !== 'https:' || !['oapi.dingtalk.com','api.dingtalk.com'].includes(url.hostname)) return;
  await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({msgtype:'text',text:{content:text}})});
}

async function openNotice(value, config) {
  const data=bytes(value.sealed);
  const key=await crypto.subtle.importKey('raw',bytes(config.ledger_key),'AES-GCM',false,['decrypt']);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:data.slice(0,12),additionalData:encoder.encode('ollie-notices:v1:'+config.state.conversation_id),tagLength:128},key,data.slice(12));
  return JSON.parse(new TextDecoder().decode(plain));
}

async function activeNotices(config, actor) {
  const url=sourceEndpoint(config);url.searchParams.set('key','like.ollieNotice:*');url.searchParams.set('select','key,value');url.searchParams.set('limit','500');
  const response=await fetch(url,{headers:{apikey:config.source.anon_key,Authorization:'Bearer '+config.source.anon_key}});
  if (!response.ok) throw new Error('Không đọc được danh sách; hãy thử lại.');
  const rows=await response.json();
  if (!Array.isArray(rows) || rows.length>=500) throw new Error('Danh sách quá lớn; cần thu gọn dữ liệu lịch sử trước khi quản lý qua chat.');
  const events=(await Promise.all(rows.map(row=>openNotice(row.value,config)))).filter(event=>event.operation!=='settings');
  const tasks=new Map();
  for (const event of events.sort((a,b)=>a.recorded_at-b.recorded_at || a.event_id.localeCompare(b.event_id))) {
    const previous=tasks.get(event.task_source_event);
    tasks.set(event.task_source_event,{...event,done:{...previous?.done,...event.done},cancelled:!!previous?.cancelled || !!event.cancelled});
  }
  return (await Promise.all([...tasks.values()].map(async event=>({...event,code:(await hash(event.task_source_event)).slice(0,8)}))))
    .filter(event=>!event.cancelled && event.deadline*1000>Date.now() && (actor===config.state.leader_staff_id || event.assignees.includes(actor)))
    .sort((a,b)=>a.deadline-b.deadline || a.created_at-b.created_at);
}

export default {
  async fetch(request, env, context) {
    if (request.method === 'GET') return json({service:'Ollie_MT notice receiver', configured:!!env.OLLIE_CONFIG_JSON});
    if (request.method !== 'POST') return json({code:'method_not_allowed'},405);
    let config;
    try { config=JSON.parse(env.OLLIE_CONFIG_JSON); sourceEndpoint(config); } catch { return json({code:'configuration_missing'},503); }
    if (!await verifySignature(request,config.credentials.appSecret)) return json({code:'invalid_signature'},401);
    const raw = await request.text(); if (encoder.encode(raw).length > 64000) return json({code:'message_too_large'},413);
    let body; try { body=JSON.parse(raw); } catch { return json({code:'invalid_json'},400); }
    if (body.robotCode && body.robotCode !== config.state.robot_code) return json({code:'wrong_bot'},403);
    if (String(body.conversationType) === '2' && body.conversationId !== config.state.conversation_id) return json({code:'wrong_group'},403);
    const actor=body.senderStaffId;
    const text=String(body.text?.content || '').replace(/@Ollie_MT\b/gi,'').trim();
    const respond = message => { context.waitUntil(replySession(body,message)); return json({}); };
    const known=[...Object.values(config.settings.trainer_recipients).map(value=>value.target),config.state.leader_staff_id];
    if (!known.includes(actor)) return respond('Tài khoản này chưa thuộc danh sách Trainer đã xác nhận.');
    const command=fold(text);
    const id=body.msgId || body.messageId;
    if (!id || typeof id !== 'string' || id.length > 512) return json({code:'message_identity_missing'},400);
    const created=Number(body.createAt || Date.now());
    if (command==='bat nhac viec' || command==='tat nhac viec') {
      if (actor!==config.state.leader_staff_id) return respond('Chỉ Nghĩa được bật hoặc tạm dừng lịch nhắc.');
      try {
        const enabled=command==='bat nhac viec';
        if (await storeNotice({event_id:'http-settings:'+id,operation:'settings',author:actor,recorded_at:created/1000,enabled},config))
          return respond(enabled ? 'Đã bật lịch gửi 08:00 hằng ngày.' : 'Đã tạm dừng lịch gửi; công việc vẫn được lưu.');
        return json({});
      } catch { return json({code:'notice_write_waiting'},503); }
    }
    if (/^(xin chao|chao|hello|hi)$/.test(command)) return respond('Xin chào! Mình là Ollie_MT. Gõ “hướng dẫn” để xem cách lưu thông báo và quản lý deadline.');
    const complete=command.match(/^hoan thanh cv-([a-f0-9]{8})$/);
    const cancel=command.match(/^huy cv-([a-f0-9]{8})$/);
    const change=command.match(/^doi han cv-([a-f0-9]{8})\s+(.+)$/);
    if (command==='danh sach' || command==='viec cua toi' || complete || cancel || change) {
      try {
        const tasks=await activeNotices(config,actor);
        if (command==='danh sach' || command==='viec cua toi') {
          const pending=tasks.filter(event=>actor===config.state.leader_staff_id ? event.assignees.some(sid=>!event.done[sid]) : !event.done[actor]);
          return respond(pending.length ? pending.map((event,index)=>`${index+1}. CV-${event.code}: ${event.content}\nHạn: ${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(event.deadline*1000))}`).join('\n\n') : 'Hiện không có thông báo còn hạn cần hoàn thành.');
        }
        if ((cancel || change) && actor!==config.state.leader_staff_id) return respond('Chỉ Nghĩa được đổi hạn hoặc hủy thông báo.');
        const code=(complete || cancel || change)[1];const matches=tasks.filter(event=>event.code===code);
        if (matches.length!==1) return respond('Không xác định được thông báo; gửi “danh sách” để lấy mã CV chính xác.');
        const event={...matches[0],event_id:'http-control:'+id,author:actor,recorded_at:created/1000};delete event.code;
        if (complete) {
          event.operation='complete';
          for (const sid of actor===config.state.leader_staff_id ? event.assignees : [actor]) event.done[sid]=created/1000;
        } else if (cancel) { event.operation='cancel';event.cancelled=true; }
        else { event.operation='change';event.deadline=parseNotice('THÔNG BÁO CẬP NHẬT\nDeadline: '+change[2],created).deadline; }
        if (await storeNotice(event,config)) return respond(complete ? 'Đã ghi nhận hoàn thành; dừng nhắc phần việc đã hoàn thành.' : cancel ? 'Đã hủy thông báo; dừng nhắc.' : 'Đã cập nhật deadline; danh sách sẽ dùng thời hạn mới.');
        return json({});
      } catch (error) { return respond('Chưa cập nhật: '+(error.message.startsWith('notice_') ? 'nguồn dữ liệu chưa sẵn sàng, hãy thử lại.' : error.message)); }
    }
    if (!command.includes('thong bao')) return respond('Nghĩa gửi @Ollie_MT kèm THÔNG BÁO và Deadline: ngày/tháng/năm giờ:phút. Các lệnh quản lý: danh sách; hoàn thành CV-<mã>; hủy CV-<mã>; đổi hạn CV-<mã> ngày/tháng/năm giờ:phút. Lịch nhắc: 08:00 Việt Nam từ sáng hôm sau.');
    if (actor !== config.state.leader_staff_id) return respond('Chỉ Nghĩa được tạo thông báo giao việc cho Team.');
    if (String(body.conversationType)!=='2') return respond('Để giao việc cho cả Team, hãy đăng thông báo trong nhóm AE CÂY KHẾ CHUA và @Ollie_MT.');
    let notice;
    try { notice=parseNotice(text,created); } catch (error) { return respond('Chưa lưu: ' + error.message); }
    const assignees=[...new Set([...Object.values(config.settings.trainer_recipients).map(value=>value.target),config.state.leader_staff_id])];
    const event={event_id:'http:'+id, task_source_event:'http:'+id, operation:'create', author:actor,
      content:notice.content, original:text, deadline:notice.deadline, created_at:created/1000,
      recorded_at:created/1000, cancelled:false, assignees, done:{}};
    try {
      if (await storeNotice(event,config)) return respond('Đã lưu thông báo.\nDeadline: '+notice.shown+'\nNhắc 13 Trainer và Nghĩa lúc 08:00 hằng ngày, từ sáng hôm sau đến deadline.');
      return json({});
    } catch { return json({code:'notice_write_waiting'},503); }
  }
};
