// Both public dashboards call one authenticated TikTok API controller.
const proxyOrigin='https://centraltraining.github.io';
const proxyHeaders={'Content-Type':'application/json','Cache-Control':'no-store','Referrer-Policy':'no-referrer','Access-Control-Allow-Origin':proxyOrigin,'Access-Control-Allow-Headers':'content-type,apikey,authorization','Access-Control-Allow-Methods':'POST,OPTIONS','Vary':'Origin'};
export function proxyReply(value,status=200){return new Response(JSON.stringify(value),{status,headers:proxyHeaders});}
export async function sharedApiProxy(req,raw,base,callback=false){
 try{
  const target=new URL(base+'/functions/v1/trainer-channel-api'+(callback?'/oauth/callback':''));
  if(callback)target.search=new URL(req.url).search;
  const response=await fetch(target.href,{method:callback?'GET':'POST',headers:{'Content-Type':'application/json'},...(callback?{}:{body:raw}),redirect:callback?'manual':'error',signal:AbortSignal.timeout(105000)});
  if(callback&&[302,303].includes(response.status)){
   const location=response.headers.get('location')||'',destination=new URL(location);
   const site=/^https:\/\/centraltraining\.github\.io\/(Test|Dashboard)\/#channel-connect=(ok|failed)$/.test(location);
   const native=destination.origin===new URL(base).origin&&destination.pathname==='/functions/v1/trainer-channel/oauth/callback';
   if(!site&&!native)return proxyReply({error:'Địa chỉ quay lại không hợp lệ.'},502);
   return new Response(null,{status:303,headers:{Location:location,'Cache-Control':'no-store','Referrer-Policy':'no-referrer'}});
  }
  const out=await response.json();
  if(!out||typeof out!=='object'||Array.isArray(out))return proxyReply({error:'Phản hồi TikTok API chưa hợp lệ.'},502);
  return proxyReply(out,response.status);
 }catch{return proxyReply({error:'Chưa kết nối được TikTok API. Dữ liệu đã lưu được giữ nguyên.'},502);}
}
