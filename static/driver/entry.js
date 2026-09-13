'use strict';
(() => {
 window.addEventListener('hashchange',()=>location.reload());
 const params=new URLSearchParams(location.hash.slice(1)),direction=params.has('exit')?'exit':'entry',token=params.get(direction);
 if(direction==='exit'){document.querySelector('#entry-panel h2').textContent='Xác nhận xe ra bãi';document.querySelector('#entry-panel p').textContent='Chỉ xác nhận khi xe của bạn đang chờ tại cổng ra.';document.querySelector('#confirm-entry').textContent='Xác nhận ra bãi';document.querySelector('#entry-notice').textContent='Đăng nhập hoặc tạo tài khoản để xác nhận ra bãi.';}
 const panel=document.querySelector('#entry-panel'),notice=document.querySelector('#entry-notice'),button=document.querySelector('#confirm-entry'),result=document.querySelector('#entry-result');
 if(!token)return;
 notice.hidden=false;
 if(!/^[a-f0-9]{48}$/.test(token)){notice.textContent='Mã QR không hợp lệ. Vui lòng quét lại mã trên máy tính bảng tại cổng.';return;}
 const storageKey='qr-confirm:'+direction+':'+token;
 let expires=Number(sessionStorage.getItem(storageKey));
 if(!expires){expires=Date.now()+60000;sessionStorage.setItem(storageKey,String(expires));}
 let done=false,pending=false,expired=false;
 const countdown=document.createElement('p');countdown.id='entry-countdown';countdown.setAttribute('role','timer');button.before(countdown);
 const rescan=document.createElement('button');rescan.type='button';rescan.className='secondary';rescan.textContent='Quét lại QR';rescan.hidden=true;result.after(rescan);
 rescan.onclick=()=>{panel.hidden=true;document.querySelector('#scan-qr').click();};
 panel.classList.add('confirmation-overlay');panel.setAttribute('role','dialog');panel.setAttribute('aria-label',direction==='exit'?'Xác nhận ra bãi':'Xác nhận vào bãi');
 function tick(){if(done)return;const remaining=Math.max(0,Math.ceil((expires-Date.now())/1000));countdown.textContent='Thời gian xác nhận còn '+remaining+' giây';if(!remaining){expired=true;button.disabled=true;rescan.hidden=false;result.textContent='Đã hết 1 phút. Vui lòng quét lại QR để xác nhận.';}}
 tick();const timer=setInterval(tick,250);
 function update(){notice.hidden=Boolean(user);panel.hidden=!user;}
 window.addEventListener('driver-session-change',update);update();
 button.onclick=async()=>{tick();if(pending||done||expired)return;pending=true;button.disabled=true;result.textContent='Đang kiểm tra tài khoản và chỗ trống…';try{const response=await api('/'+direction,{token});done=true;clearInterval(timer);countdown.textContent='';result.textContent=response.assigned_slot?'Bạn được xếp vào ô '+response.assigned_slot+'. Vui lòng chờ thanh chắn mở rồi di chuyển đến ô này. Ô được giữ trong 10 phút.':'Đã xác nhận tài khoản. Vui lòng chờ thanh chắn mở trước khi di chuyển.';if(response.assigned_slot){selected=response.assigned_slot;panel.querySelector("h2").textContent="Vị trí của bạn: "+response.assigned_slot;}button.textContent=direction==='exit'?'Đã xác nhận ra bãi':'Đã xác nhận vào bãi';rescan.textContent='Đóng';rescan.hidden=false;rescan.onclick=()=>{panel.hidden=true;};history.replaceState(null,'',location.pathname);await refresh();}catch(e){result.textContent=vietnameseError(e);}finally{pending=false;button.disabled=done||expired;}};
})();
