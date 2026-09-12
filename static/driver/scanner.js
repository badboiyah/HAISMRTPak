'use strict';
(() => {
 const video=document.querySelector('#scan-video'),box=document.querySelector('#scanner'),status=document.querySelector('#scan-status'),start=document.querySelector('#scan-qr');
 const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d',{willReadFrequently:true});
 let stream=null,running=false,timer=null;
 function stop(){running=false;clearTimeout(timer);if(stream)stream.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;box.hidden=true;start.disabled=false;}
 function decode(){
  if(!running)return;
  if(video.readyState>=2&&video.videoWidth){
   canvas.width=Math.min(video.videoWidth,640);canvas.height=Math.round(video.videoHeight*canvas.width/video.videoWidth);ctx.drawImage(video,0,0,canvas.width,canvas.height);
   const pixels=ctx.getImageData(0,0,canvas.width,canvas.height),code=jsQR(pixels.data,canvas.width,canvas.height);
   if(code){try{const url=new URL(code.data);const token=new URLSearchParams(url.hash.slice(1)).get('entry');if(url.origin!==location.origin||url.pathname!='/driver/'||!/^[a-f0-9]{48}$/.test(token||''))throw Error();stop();location.assign('/driver/#entry='+token);return;}catch{status.textContent='Mã này không phải mã vào bãi. Hãy quét mã trên máy tính bảng tại cổng.';}}
  }
  timer=setTimeout(decode,180);
 }
 start.onclick=async()=>{
  if(running)return;running=true;start.disabled=true;status.textContent='Đang mở camera…';
  try{if(!navigator.mediaDevices?.getUserMedia)throw Error();const media=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});if(!running){media.getTracks().forEach(t=>t.stop());return;}stream=media;video.srcObject=stream;box.hidden=false;await video.play();status.textContent='Đưa mã QR tại cổng vào khung camera.';decode();}
  catch{stop();status.textContent='Không mở được camera. Hãy cấp quyền camera cho ứng dụng hoặc dùng camera điện thoại quét mã QR tại cổng.';}
 };
 document.querySelector('#stop-scan').onclick=stop;
 window.addEventListener('pagehide',stop);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
})();
