// Only fixed, server-configured Sandbox slots are accepted. Keys never reach the browser.
export const SANDBOX_IDS=['primary','secondary'];
export const sandboxId=value=>value===undefined||value===null?'primary':SANDBOX_IDS.includes(value)?value:null;
export function sandboxCredentials(id,get){
 if(!SANDBOX_IDS.includes(id))throw Error('Unknown Sandbox');
 if(id==='secondary')return {client:get('TIKTOK_TEST_SANDBOX2_CLIENT_KEY')?.trim(),clientSecret:get('TIKTOK_TEST_SANDBOX2_CLIENT_SECRET')?.trim(),credentialSource:'sandbox2'};
 const testClient=get('TIKTOK_TEST_CLIENT_KEY'),testSecret=get('TIKTOK_TEST_CLIENT_SECRET'),useTest=testClient!==undefined||testSecret!==undefined;
 return {client:(useTest?testClient:get('TIKTOK_CLIENT_KEY'))?.trim(),clientSecret:(useTest?testSecret:get('TIKTOK_CLIENT_SECRET'))?.trim(),credentialSource:useTest?'test':'legacy'};
}
