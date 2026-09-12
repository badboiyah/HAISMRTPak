'use strict';
(() => {
 window.addEventListener('hashchange',()=>location.reload());
 const params=new URLSearchParams(location.hash.slice(1)),direction=params.has('exit')?'exit':'entry',token=params.get(direction);
 if(direction==='exit'){document.querySelector('#entry-panel h2').textContent='Xác nhận xe ra bãi';document.querySelector('#entry-panel p').textContent='Chỉ xác nhận khi xe của bạn đang chờ tại cổng ra.';document.querySelector('#confirm-entry').textContent='Xác nhận ra bãi';document.querySelector('#entry-notice').textContent='Đăng nhập hoặc tạo tài khoản để xác nhận ra bãi.';}
 const panel=document.querySelector('#entry-panel'),notice=document.querySelector('#entry-notice'),button=document.querySelector('#confirm-entry'),result=document.querySelector('#entry-result');
 if(!token)return;
 notice.hidden=false;
 if(!/^[a-f0-9]{48}$/.test(token)){notice.textContent='Mã QR không hợp lệ. Vui lòng quét lại mã trên máy tính bảng tại cổng.';return;}
 let done=false,pending=false;
 function update(){notice.hidden=Boolean(user);panel.hidden=!user;}
 window.addEventListener('driver-session-change',update);update();
 button.onclick=async()=>{if(pending||done)return;pending=true;button.disabled=true;result.textContent='Đang kiểm tra tài khoản và chỗ trống…';try{const response=await api('/'+direction,{token});done=true;result.textContent='Đã xác nhận tài khoản. Vui lòng chờ thanh chắn mở trước khi di chuyển.';button.textContent=direction==='exit'?'Đã xác nhận ra bãi':'Đã xác nhận vào bãi';history.replaceState(null,'',location.pathname);await refresh();}catch(e){result.textContent=vietnameseError(e);}finally{pending=false;button.disabled=done;}};
})();
