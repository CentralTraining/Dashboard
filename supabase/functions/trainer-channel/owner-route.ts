// A signed internal request keeps legacy Main grants with their original owner.
const ownerEncoder=new TextEncoder();
const ownerBytes=value=>Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
const ownerText=value=>btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
async function ownerKey(secret){
 const key=await crypto.subtle.digest('SHA-256',ownerEncoder.encode('trainer-channel-native-main-v1:'+secret));
 return crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
}
export async function nativeMainHeaders(raw,secret){
 const at=String(Date.now()),payload=ownerEncoder.encode(at+'\n'+raw);
 const signature=await crypto.subtle.sign('HMAC',await ownerKey(secret),payload);
 return {'x-channel-owner-at':at,'x-channel-owner-signature':ownerText(signature)};
}
export async function nativeMainRequest(req,raw,secret){
 try{
  const at=req.headers.get('x-channel-owner-at')||'',signature=req.headers.get('x-channel-owner-signature')||'';
  if(!/^\d{13}$/.test(at)||Math.abs(Date.now()-Number(at))>120000||!/^[A-Za-z0-9_-]{43}$/.test(signature))return false;
  return await crypto.subtle.verify('HMAC',await ownerKey(secret),ownerBytes(signature),ownerEncoder.encode(at+'\n'+raw));
 }catch{return false;}
}
