'use strict';
(() => {
 window.addEventListener('hashchange',()=>location.reload());
 const token=new URLSearchParams(location.hash.slice(1)).get('entry');
 const panel=document.querySelector('#entry-panel'),notice=document.querySelector('#entry-notice'),button=document.querySelector('#confirm-entry'),result=document.querySelector('#entry-result');
 if(!token)return;
 notice.hidden=false;
 if(!/^[a-f0-9]{48}$/.test(token)){notice.textContent='Mã QR không hợp lệ. Vui lòng quét lại mã trên máy tính bảng tại cổng.';return;}
 let done=false,pending=false;
 function update(){notice.hidden=Boolean(user);panel.hidden=!user;}
 window.addEventListener('driver-session-change',update);update();
 button.onclick=async()=>{if(pending||done)return;pending=true;button.disabled=true;result.textContent='Đang kiểm tra tài khoản và chỗ trống…';try{const response=await api('/entry',{token});done=true;result.textContent='Đã xác nhận tài khoản cho lượt vào bãi. Vui lòng chờ thanh chắn mở trước khi di chuyển.';button.textContent='Đã xác nhận vào bãi';history.replaceState(null,'',location.pathname);await refresh();}catch(e){result.textContent=vietnameseError(e);}finally{pending=false;button.disabled=done;}};
})();
