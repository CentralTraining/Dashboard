(function () {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function validateDraft(content, localDeadline, link, trainerIds, now = Date.now()) {
    content = String(content).trim(); link = String(link || '').trim();
    if (!content || content.length > 2000) throw new Error('Nội dung cần từ 1 đến 2000 ký tự.');
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(localDeadline)) throw new Error('Chọn ngày và giờ hoàn thành theo giờ Việt Nam.');
    const deadline = localDeadline + ':00+07:00'; const parsed = new Date(deadline);
    if (!Number.isFinite(parsed.getTime()) || parsed.getTime() <= now) throw new Error('Deadline phải ở trong tương lai.');
    if (link && !['https:', 'http:'].includes(new URL(link).protocol)) throw new Error('Link cần bắt đầu bằng https:// hoặc http://.');
    if (!trainerIds.length) throw new Error('Chưa chọn Trainer nhận việc.');
    return {content, deadline, link, trainer_ids:[...new Set(trainerIds)]};
  }
  if (typeof module !== 'undefined') module.exports = {validateDraft};
  if (typeof document === 'undefined') return;

  async function rows(prefix) {
    if (!SUPABASE_URL) return Object.keys(localStorage).filter(key => key.startsWith(prefix)).map(key => ({key,value:JSON.parse(localStorage.getItem(key))}));
    const result = [];
    for (let offset = 0; offset < 10000; offset += 500) {
      const url = new URL('/rest/v1/' + SUPABASE_TABLE, SUPABASE_URL);
      url.searchParams.set('key', 'like.' + prefix + '*'); url.searchParams.set('select', 'key,value');
      url.searchParams.set('order', 'key.asc'); url.searchParams.set('limit', '500'); url.searchParams.set('offset',String(offset));
      const response = await fetch(url, {headers:SUPA_HEADERS_});
      if (!response.ok) throw new Error('Không đọc được danh sách công việc.');
      const data = await response.json(); if (!Array.isArray(data)) throw new Error('Nguồn công việc không hợp lệ.');
      result.push(...data); if (data.length < 500) return result;
    }
    throw new Error('Danh sách quá lớn; cần thu gọn công việc cũ.');
  }
  async function save(key,value) { if (!await dbSet(key,value)) throw new Error('Chưa lưu được; hãy kiểm tra kết nối rồi thử lại.'); }
  const showDate = value => new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(value));
  let selection = 0;
  async function render(trainerId) {
    const token = ++selection;
    const body = document.getElementById('homeDetailBody'); if (!body) return;
    document.getElementById('ollie-deadline-panel')?.remove();
    const panel = document.createElement('section'); panel.id = 'ollie-deadline-panel';
    panel.style.cssText = 'margin-top:20px;padding:18px;border:1px solid #dfece5;border-radius:14px;background:#fff';
    panel.innerHTML = '<h3 style="margin:0 0 8px;color:#07543b">📅 Công việc &amp; deadline</h3><p style="font-size:12px;color:#66776f">Ollie_MT nhắc lúc 08:00 từ sáng hôm sau đến deadline. Giờ trên biểu mẫu là giờ Việt Nam.</p><p role="status">Đang tải công việc…</p>';
    body.append(panel);
    const admin = typeof isAdmin === 'function' && isAdmin();
    const canComplete = admin || (typeof isTrainer === 'function' && isTrainer() && session?.trainerId === trainerId);
    try {
      const [allTasks, allDone] = await Promise.all([rows('ollieTask:'), rows('ollieDone:')]);
      if (token !== selection || !panel.isConnected) return;
      const done = Object.fromEntries(allDone.map(row => [row.key,row.value]));
      const tasks = allTasks.map(row=>row.value).filter(value => value && !value.cancelled && value.trainer_ids?.includes(trainerId))
        .sort((a,b)=>Date.parse(a.deadline)-Date.parse(b.deadline) || Date.parse(a.created_at)-Date.parse(b.created_at));
      const draft = admin ? `<form style="display:grid;gap:9px;margin-bottom:16px">
        <textarea name="content" maxlength="2000" rows="3" placeholder="Nội dung cần hoàn thành" required style="width:100%;box-sizing:border-box;padding:9px;border:1px solid #dfece5;border-radius:8px"></textarea>
        <label>Thời gian hoàn thành (Việt Nam) <input name="deadline" type="datetime-local" required style="padding:7px"></label>
        <input name="link" type="url" placeholder="Link tham khảo (không bắt buộc)" style="padding:9px;border:1px solid #dfece5;border-radius:8px">
        <select name="audience" style="padding:7px"><option value="one">Trainer này</option><option value="all">Tất cả Trainer</option></select>
        <button type="submit" style="justify-self:start;padding:8px 14px;border:0;border-radius:8px;background:#0b8059;color:white">Lưu việc nhắc</button>
        <p role="status" style="margin:0;font-size:12px"></p></form>` : '';
      const cards = tasks.map(task => {
        const completed = done['ollieDone:'+task.id+':'+trainerId]?.done === true;
        const expired = Date.parse(task.deadline) <= Date.now();
        const link = task.link && /^https?:\/\//i.test(task.link) ? ` · <a href="${escape(task.link)}" target="_blank" rel="noopener noreferrer" style="color:#c0392b;font-weight:700">Link</a>` : '';
        return `<div style="padding:12px 0;border-top:1px solid #edf2ef" data-task="${escape(task.id)}">
          <div style="white-space:pre-wrap;${completed?'text-decoration:line-through;color:#7a858e':''}">${escape(task.content)}</div>
          <p style="margin:5px 0;font-size:12px">⏰ ${escape(showDate(task.deadline))}${link} ${completed?' · ✓ Đã hoàn thành':expired?' · Quá hạn':''}</p>
          ${canComplete?`<button type="button" data-complete="${completed?'no':'yes'}">${completed?'Đánh dấu chưa xong':'Đã hoàn thành'}</button>`:''}
          ${admin?'<button type="button" data-cancel style="margin-left:8px">Hủy việc</button>':''}
        </div>`;
      }).join('');
      panel.querySelector('[role="status"]').outerHTML = draft + (cards || '<p style="font-size:13px;color:#7a858e">Chưa có công việc đặt deadline trên dashboard cho Trainer này.</p>');
      const form = panel.querySelector('form');
      if (form) form.addEventListener('submit',async event => {
        event.preventDefault(); const button=form.querySelector('button');const status=form.querySelector('[role="status"]');button.disabled=true;
        try {
          const trainerIds=form.elements.audience.value==='all'?config.trainers.map(value=>value.id):[trainerId];
          const value=validateDraft(form.elements.content.value,form.elements.deadline.value,form.elements.link.value,trainerIds);
          value.id=crypto.randomUUID();value.created_at=new Date().toISOString();value.cancelled=false;
          await save('ollieTask:'+value.id,value); await render(trainerId);
        } catch(error) { status.textContent=error.message;button.disabled=false; }
      });
      panel.querySelectorAll('[data-task]').forEach(card => {
        const task=tasks.find(value=>value.id===card.dataset.task);
        card.querySelector('[data-complete]')?.addEventListener('click',async event => {
          event.target.disabled=true;
          try { await save('ollieDone:'+task.id+':'+trainerId,{done:event.target.dataset.complete==='yes',updated_at:new Date().toISOString()});await render(trainerId); }
          catch(error) { event.target.disabled=false;alert(error.message); }
        });
        card.querySelector('[data-cancel]')?.addEventListener('click',async event => {
          if (!confirm('Hủy việc này cho toàn bộ Trainer được giao?')) return;
          event.target.disabled=true;
          try { await save('ollieTask:'+task.id,{...task,cancelled:true});await render(trainerId); }
          catch(error) { event.target.disabled=false;alert(error.message); }
        });
      });
    } catch(error) { panel.querySelector('[role="status"]').textContent=error.message; }
  }
  if (typeof openHomeDetailPopup_ === 'function') {
    const original = openHomeDetailPopup_;
    window.openHomeDetailPopup_ = async function(trainerId) { await original(trainerId);await render(trainerId); };
  }
})();
