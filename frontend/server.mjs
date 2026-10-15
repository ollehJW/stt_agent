import http from 'node:http';
import {createReadStream} from 'node:fs';
import {stat,realpath} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve,sep,extname} from 'node:path';
const root=await realpath(fileURLToPath(new URL('./dist',import.meta.url)));
const target=new URL(process.env.BACKEND_ORIGIN||'http://127.0.0.1:1015');
if(target.protocol!=='http:'||!['localhost','127.0.0.1'].includes(target.hostname))throw new Error('Backend must be local');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2','.png':'image/png','.ico':'image/x-icon','.mp4':'video/mp4','.pdf':'application/pdf'};
const hop=new Set(['connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade']);
function clean(headers){const blocked=new Set([...hop,...String(headers.connection||'').toLowerCase().split(',').map(v=>v.trim())]);return Object.fromEntries(Object.entries(headers).filter(([k])=>!blocked.has(k)));}
function error(res,status,message){if(res.headersSent)return res.destroy();res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail:message}));}
const server=http.createServer(async(req,res)=>{
 res.setHeader('X-Content-Type-Options','nosniff');
 let url,path;
 try{url=new URL(req.url,'http://localhost');path=decodeURIComponent(url.pathname);}catch{return error(res,400,'Invalid URL');}
 if(path==='/wiavoice'||path.startsWith('/wiavoice/'))path=path.slice(9)||'/';
 if(path.startsWith('/api/')){
  if(Number(req.headers['content-length']||0)>21*1024*1024)return error(res,413,'파일은 최대 20MB까지 첨부할 수 있습니다.');
  const headers=clean(req.headers);headers.host=target.host;
  const upstream=http.request({hostname:target.hostname,port:target.port,path:path+url.search,method:req.method,headers},reply=>{
   res.writeHead(reply.statusCode,clean(reply.headers));reply.pipe(res);reply.on('error',()=>res.destroy());
  });
  let bytes=0;req.on('data',chunk=>{bytes+=chunk.length;if(bytes>21*1024*1024){error(res,413,'파일은 최대 20MB까지 첨부할 수 있습니다.');upstream.destroy();}});
  upstream.setTimeout(120000,()=>upstream.destroy());upstream.on('error',()=>error(res,502,'서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'));
  req.on('aborted',()=>upstream.destroy());res.on('close',()=>{if(!res.writableEnded)upstream.destroy();});req.pipe(upstream);return;
 }
 if(!['GET','HEAD'].includes(req.method))return error(res,405,'Method not allowed');
 if(path.split('/').some(x=>x.startsWith('.')))return error(res,404,'Not found');
 try{
  let file=resolve(root,'.'+path);if(file!==root&&!file.startsWith(root+sep))return error(res,403,'Forbidden');
  let info;try{info=await stat(file);}catch{}
  if(!info?.isFile()){if(extname(path)||path.startsWith('/assets/')||path.startsWith('/fonts/'))return error(res,404,'Not found');file=resolve(root,'index.html');info=await stat(file);}
  file=await realpath(file);if(!file.startsWith(root+sep))return error(res,403,'Forbidden');
  const headers={'Content-Type':mime[extname(file)]||'application/octet-stream','Content-Length':info.size,'Cache-Control':path.startsWith('/assets/')?'public, max-age=31536000, immutable':'no-cache'};
  let status=200,options;
  if(extname(file)==='.mp4') {
   headers['Content-Type']='video/mp4';headers['Accept-Ranges']='bytes';
   if(req.method==='GET' && req.headers.range) {
    const match=/^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
    let start,end;
    if(match && (match[1] || match[2])) {
     start=match[1]?Number(match[1]):Math.max(0,info.size-Number(match[2]));
     end=match[1]&&match[2]?Math.min(Number(match[2]),info.size-1):info.size-1;
    }
    if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||start>=info.size||end<start) {
     res.writeHead(416,{'Content-Range':`bytes */${info.size}`,'Accept-Ranges':'bytes','Content-Length':'0'});return res.end();
    }
    status=206;options={start,end};headers['Content-Range']=`bytes ${start}-${end}/${info.size}`;headers['Content-Length']=end-start+1;
   }
  }
  res.writeHead(status,headers);
  if(req.method==='HEAD')return res.end();const stream=createReadStream(file,options);stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);
 }catch{error(res,500,'Unable to serve frontend');}
});
server.requestTimeout=120000;
server.listen(Number(process.env.FRONTEND_PORT||1005),'127.0.0.1',()=>console.log('WiaVoice frontend listening on '+(process.env.FRONTEND_PORT||1005)));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),10000).unref();});
