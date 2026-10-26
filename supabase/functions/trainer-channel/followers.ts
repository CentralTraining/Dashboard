// Observations come from TikTok at sync time, never from a requested report date.
export const FOLLOWER_SCOPE='user.info.stats';
export const FOLLOWER_BASELINE_DATE='2026-10-01';
const followerCalendar=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'});
export const followerDay=at=>followerCalendar.format(new Date(at));
export function followerPoints(history){
 const byTime=new Map();
 for(const p of Array.isArray(history)?history:[]){
  if(typeof p?.at!=='string'||!Number.isFinite(Date.parse(p.at))||!Number.isSafeInteger(p.count)||p.count<0)continue;
  const at=new Date(p.at).toISOString();byTime.set(at,{at,count:p.count});
 }
 return [...byTime.values()].sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
}
export function recordFollowers(history,point){
 const points=followerPoints([...(Array.isArray(history)?history:[]),point]),days=new Map();
 for(const p of points){const day=followerDay(p.at),entry=days.get(day);if(entry)entry.last=p;else days.set(day,{first:p,last:p});}
 return [...days.values()].flatMap(d=>d.first.at===d.last.at?[d.first]:[d.first,d.last]);
}
export function followerView(channel,from,to){
 const history=followerPoints(channel?.followers?.history),last=history[history.length-1],authorized=!!channel?.token?.scopes?.includes(FOLLOWER_SCOPE)&&channel?.followers?.status!=='needs_authorization';
 const saved=channel?.followerBaseline,baseline=saved?.date===FOLLOWER_BASELINE_DATE&&Number.isSafeInteger(saved.count)&&saved.count>=0&&saved.handle===channel?.handle&&(!saved.openId||saved.openId===channel?.token?.openId)?{date:saved.date,count:saved.count,source:'admin_record',recordedAt:saved.recordedAt}:null;
 return {authorized,status:!channel?.token?'not_connected':!authorized?'needs_authorization':channel.followers?.status||'awaiting_sync',
  current:last?.count??null,asOf:last?.at??null,firstRecordedAt:history[0]?.at??null,baselineDate:FOLLOWER_BASELINE_DATE,baseline,
  history:history.filter(p=>{const day=followerDay(p.at);return day>=FOLLOWER_BASELINE_DATE&&day<=to;})};
}


