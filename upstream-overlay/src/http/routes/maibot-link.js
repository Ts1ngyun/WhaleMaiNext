'use strict';
const fs = require('node:fs');
const {json,readBody}=require('../util');
const {isLoopbackRequest}=require('../security');
const {sendDenial}=require('../../core/wechatSendPolicy');
module.exports=function(router){
 router.post('/webhook/wechat',async(runtime,req,res)=>{
  const gw=runtime.gateways?.get('wechat');
  if(!isLoopbackRequest(req)||!gw?.verifyToken(req,null))return json(res,403,{ok:false,error:'invalid bridge token'});
  const b=await readBody(req);const id=String(b.chat_id||'');
  const contact=runtime.contacts?.get(id);
  const reason=sendDenial(runtime.config,{id,names:[b.chat_title,b.nickname,contact?.name,contact?.remark].filter(Boolean),isGroup:b.chat_type==='group'||id.endsWith('@chatroom')});
  if(reason)return json(res,200,{ok:true,action:'ignore',reason});
  if(runtime.config.gateway?.wechat?.enabled===false)return json(res,200,{ok:true,skipped:'adapter_disabled'});
  try{
   const cfg=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../../../data/maibot-link.json'),'utf8'));
   const token=fs.readFileSync(cfg.tokenFile,'utf8').trim();
   const r=await fetch('http://127.0.0.1:19787/native/reply',{method:'POST',headers:{'content-type':'application/json','x-hub-token':token},body:JSON.stringify(b),signal:AbortSignal.timeout(2500)});
   if(!r.ok)throw Error('MaiBot HTTP '+r.status);
   return json(res,200,await r.json());
  }catch(e){runtime.logger.error('MaiBot link: '+e.name);return json(res,503,{ok:false,error:'转发服务未确认入队'});}
 });
};
