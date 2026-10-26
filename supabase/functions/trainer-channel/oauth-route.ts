// A registered callback may route an opaque state to the owning function.
// The owner still validates, consumes and authorizes that encrypted state.
export const SHARED_CALLBACK_PATH='/functions/v1/trainer-channel-test/oauth/callback';
export const MAIN_CALLBACK_PATH='/functions/v1/trainer-channel/oauth/callback';
export const MAIN_STATE_PREFIX='main.';
export const isMainOauthState=state=>typeof state==='string'&&/^main\.[a-f0-9-]{72}$/.test(state);
export const isLegacyOauthState=state=>typeof state==='string'&&/^[a-f0-9-]{72}$/.test(state);
export function relayMainOauth(url,base){
 const state=url.searchParams.get('state');
 if(!isMainOauthState(state))return null;
 for(const key of ['state','code','error'])if(url.searchParams.getAll(key).length>1)
  return new Response('Invalid callback parameters',{status:400,headers:{'Cache-Control':'no-store','Referrer-Policy':'no-referrer'}});
 const target=new URL(MAIN_CALLBACK_PATH,base);
 for(const key of ['state','code','error'])if(url.searchParams.has(key))target.searchParams.set(key,url.searchParams.get(key));
 return new Response(null,{status:303,headers:{Location:target.href,'Cache-Control':'no-store','Referrer-Policy':'no-referrer'}});
}
